from __future__ import annotations

import collections
import datetime
import glob
import itertools
import json
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import ClassVar

import numpy as np
import pandas as pd

from sec_certs import constants
from sec_certs.dataset.json_path_dataset import JSONPathDataset
from sec_certs.sample.cpe import CPE, cached_cpe
from sec_certs.sample.cve import CVE
from sec_certs.serialization.json import ComplexSerializableType
from sec_certs.utils import helpers
from sec_certs.utils.parallel_processing import process_parallel
from sec_certs.utils.tqdm import tqdm

logger = logging.getLogger(__name__)


class CVEDataset(JSONPathDataset, ComplexSerializableType):
    CVE_URL: ClassVar[str] = "https://nvd.nist.gov/feeds/json/cve/1.1/nvdcve-1.1-"
    CPE_MATCH_FEED_URL: ClassVar[str] = "https://nvd.nist.gov/feeds/json/cpematch/1.0/nvdcpematch-1.0.json.zip"

    def __init__(self, cves: dict[str, CVE], json_path: str | Path = constants.DUMMY_NONEXISTING_PATH):
        self.cves = cves
        self.json_path = Path(json_path)
        self.cpe_to_cve_ids_lookup: dict[str, set[str]] = {}
        self.cves_with_vulnerable_configurations: list[CVE] = []

    @property
    def serialized_attributes(self) -> list[str]:
        return ["cves"]

    def __iter__(self):
        yield from self.cves.values()

    def __getitem__(self, item: str) -> CVE:
        return self.cves.__getitem__(item.upper())

    def __setitem__(self, key: str, value: CVE):
        self.cves.__setitem__(key.lower(), value)

    def __len__(self) -> int:
        return len(self.cves)

    def __eq__(self, other: object):
        return isinstance(other, CVEDataset) and self.cves == other.cves

    def _filter_cves_with_cpe_configurations(self) -> None:
        """
        Method filters the subset of CVE dataset thah contain at least one CPE configuration in the CVE.
        """
        self.cves_with_vulnerable_configurations = [cve for cve in self if cve.vulnerable_cpe_configurations]

    def build_lookup_dict(self, use_nist_mapping: bool = True, nist_matching_filepath: Path | None = None):
        """
        Builds look-up dictionary CPE -> Set[CVE] and filter the CVEs which contain CPE configurations.
        Developer's note: There are 3 CPEs that are present in the cpe matching feed, but are badly processed by CVE
        feed, in which case they won't be found as a key in the dictionary. We intentionally ignore those. Feel free
        to add corner cases and manual fixes. According to our investigation, the suffereing CPEs are:
            - CPE(uri='cpe:2.3:a:arubanetworks:airwave:*:*:*:*:*:*:*:*', title=None, version='*', vendor='arubanetworks', item_name='airwave', start_version=None, end_version=('excluding', '8.2.0.0'))
            - CPE(uri='cpe:2.3:a:bayashi:dopvcomet\\*:0009:b:*:*:*:*:*:*', title=None, version='0009', vendor='bayashi', item_name='dopvcomet\\*', start_version=None, end_version=None)
            - CPE(uri='cpe:2.3:a:bayashi:dopvstar\\*:0091:*:*:*:*:*:*:*', title=None, version='0091', vendor='bayashi', item_name='dopvstar\\*', start_version=None, end_version=None)
        """
        self.cpe_to_cve_ids_lookup = {}
        self.cves = {x.cve_id.upper(): x for x in self}

        logger.info("Getting CPE matching dictionary from NIST.gov")

        if use_nist_mapping:
            matching_dict = self.get_nist_cpe_matching_dict(nist_matching_filepath)

        cve: CVE
        for cve in tqdm(self, desc="Building-up lookup dictionaries for fast CVE matching"):
            # See note above, we use matching_dict.get(cpe, []) instead of matching_dict[cpe] as would be expected
            if use_nist_mapping:
                vulnerable_configurations = list(
                    itertools.chain.from_iterable(matching_dict.get(cpe, []) for cpe in cve.vulnerable_cpes)
                )
            else:
                vulnerable_configurations = cve.vulnerable_cpes
            for cpe in vulnerable_configurations:
                if cpe.uri not in self.cpe_to_cve_ids_lookup:
                    self.cpe_to_cve_ids_lookup[cpe.uri] = {cve.cve_id}
                else:
                    self.cpe_to_cve_ids_lookup[cpe.uri].add(cve.cve_id)

        self._filter_cves_with_cpe_configurations()

    @classmethod
    def download_cves(cls, output_path_str: str, start_year: int, end_year: int):
        output_path = Path(output_path_str)
        if not output_path.exists():
            output_path.mkdir()

        urls = [cls.CVE_URL + str(x) + ".json.zip" for x in range(start_year, end_year + 1)]

        logger.info(f"Identified {len(urls)} CVE files to fetch from nist.gov. Downloading them into {output_path}")
        with tempfile.TemporaryDirectory() as tmp_dir:
            outpaths = [Path(tmp_dir) / Path(x).name.rstrip(".zip") for x in urls]
            responses = helpers.download_parallel(urls, outpaths, "Downloading CVEs resources from NVD")

            for o, r in zip(outpaths, responses):
                if r == constants.RESPONSE_OK:
                    with zipfile.ZipFile(o, "r") as zip_handle:
                        zip_handle.extractall(output_path)

    @classmethod
    def from_nist_json(cls, input_path: str) -> CVEDataset:
        with Path(input_path).open("r") as handle:
            data = json.load(handle)
        cves = [CVE.from_nist_dict(x) for x in data["CVE_Items"]]
        return cls({x.cve_id: x for x in cves})

    @classmethod
    def from_web(
        cls,
        start_year: int = 2002,
        end_year: int = datetime.datetime.now().year,
        json_path: str | Path = constants.DUMMY_NONEXISTING_PATH,
    ):
        logger.info("Building CVE dataset from nist.gov website.")
        with tempfile.TemporaryDirectory() as tmp_dir:
            cls.download_cves(tmp_dir, start_year, end_year)
            json_files = glob.glob(tmp_dir + "/*.json")

            logger.info("Downloaded required resources. Building CVEDataset from jsons.")
            results = process_parallel(
                cls.from_nist_json,
                json_files,
                use_threading=False,
                progress_bar_desc="Building CVEDataset from jsons",
            )
        return cls(dict(collections.ChainMap(*(x.cves for x in results))), json_path)

    def _get_cve_ids_for_cpe_uri(self, cpe_uri: str) -> set[str]:
        return self.cpe_to_cve_ids_lookup.get(cpe_uri, set())

    def _get_cves_from_exactly_matched_cpes(self, cpe_uris: set[str]) -> set[str]:
        return set(itertools.chain.from_iterable([self._get_cve_ids_for_cpe_uri(cpe_uri) for cpe_uri in cpe_uris]))

    def _get_cves_from_cpe_configurations(self, cpe_uris: set[str]) -> set[str]:
        return {
            cve.cve_id
            for cve in self.cves_with_vulnerable_configurations
            if any(configuration.matches(cpe_uris) for configuration in cve.vulnerable_cpe_configurations)
        }

    def get_cves_from_matched_cpes(self, cpe_uris: set[str]) -> set[str]:
        """
        Method returns the set of CVEs which are matched to the set of CPEs.
        First are matched the classic CPEs to CVEs with lookup dict and then are matched the
        'AND' type CPEs containing platform.
        """
        return {
            *self._get_cves_from_exactly_matched_cpes(cpe_uris),
            *self._get_cves_from_cpe_configurations(cpe_uris),
        }

    def filter_related_cpes(self, relevant_cpes: set[CPE]):
        """
        Since each of the CVEs is related to many CPEs, the dataset size explodes (serialized). For certificates,
        only CPEs within sample dataset are relevant. This function modifies all CVE elements. Specifically, it
        deletes all CPE records unless they are part of relevant_cpe_uris.
        :param relevant_cpes: List of relevant CPEs to keep in CVE dataset.
        """
        total_deleted_cpes = 0
        cve_ids_to_delete = []
        for cve in self:
            n_cpes_orig = len(cve.vulnerable_cpes)
            cve.vulnerable_cpes = [x for x in cve.vulnerable_cpes if x in relevant_cpes]
            cve.vulnerable_cpe_configurations = [
                x
                for x in cve.vulnerable_cpe_configurations
                if x.platform.uri in relevant_cpes and any(y.uri in relevant_cpes for y in x.cpes)
            ]

            total_deleted_cpes += n_cpes_orig - len(cve.vulnerable_cpes)
            if not cve.vulnerable_cpes:
                cve_ids_to_delete.append(cve.cve_id)

        for cve_id in cve_ids_to_delete:
            del self.cves[cve_id]
        logger.info(
            f"Totally deleted {total_deleted_cpes} irrelevant CPEs and {len(cve_ids_to_delete)} CVEs from CVEDataset."
        )

    def to_pandas(self) -> pd.DataFrame:
        df = pd.DataFrame([x.pandas_tuple for x in self], columns=CVE.pandas_columns)
        df.cwe_ids = df.cwe_ids.map(lambda x: x if x else np.nan)
        return df.set_index("cve_id")

    def get_nist_cpe_matching_dict(self, input_filepath: Path | None) -> dict[CPE, list[CPE]]:
        """
        Computes dictionary that maps complex CPEs to list of simple CPEs.
        """

        def parse_key_cpe(field: dict) -> CPE:
            start_version = None
            if "versionStartIncluding" in field:
                start_version = ("including", field["versionStartIncluding"])
            elif "versionStartExcluding" in field:
                start_version = ("excluding", field["versionStartExcluding"])

            end_version = None
            if "versionEndIncluding" in field:
                end_version = ("including", field["versionEndIncluding"])
            elif "versionEndExcluding" in field:
                end_version = ("excluding", field["versionEndExcluding"])

            return cached_cpe(field["cpe23Uri"], start_version=start_version, end_version=end_version)

        def parse_values_cpe(field: dict) -> list[CPE]:
            return [cached_cpe(x["cpe23Uri"]) for x in field["cpe_name"]]

        logger.debug("Attempting to get NIST mapping file.")
        if not input_filepath or not input_filepath.is_file():
            logger.debug("NIST mapping file not available, going to download.")
            with tempfile.TemporaryDirectory() as tmp_dir:
                filename = Path(self.CPE_MATCH_FEED_URL).name
                download_path = Path(tmp_dir) / filename
                unzipped_path = Path(tmp_dir) / filename.rstrip(".zip")
                helpers.download_file(self.CPE_MATCH_FEED_URL, download_path)

                with zipfile.ZipFile(download_path, "r") as zip_handle:
                    zip_handle.extractall(tmp_dir)
                with unzipped_path.open("r") as handle:
                    match_data = json.load(handle)
                if input_filepath:
                    logger.debug(f"Copying attained NIST mapping file to {input_filepath}")
                    shutil.move(str(unzipped_path), str(input_filepath))
        else:
            with input_filepath.open("r") as handle:
                match_data = json.load(handle)

        mapping_dict = {}
        for match in tqdm(match_data["matches"], desc="parsing cpe matching (by NIST) dictionary"):
            key = parse_key_cpe(match)
            value = parse_values_cpe(match)
            mapping_dict[key] = value if value else [key]

        return mapping_dict
