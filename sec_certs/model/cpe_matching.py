from sklearn.base import BaseEstimator
from typing import Dict, Tuple, Set, List, Optional, Union
from sec_certs.sample.cpe import CPE
import sec_certs.helpers as helpers
import tqdm
import itertools
import re
from rapidfuzz import process, fuzz
import operator
from pathlib import Path
import json
import logging
from packaging.version import parse

logger = logging.getLogger(__name__)


class CPEClassifier(BaseEstimator):
    """
    Class that can predict CPE matches for certificate instances.
    Adheres to sklearn BaseEstimator interface.
    Fit method is called on list of CPEs and build two look-up dictionaries, see description of attributes.
    """
    vendor_to_versions_: Dict[str, Set[str]]  # Key: CPE vendor, Value: versions of all CPE records of that vendor
    vendor_version_to_cpe_: Dict[Tuple[str, str], Set[CPE]] # Key: (CPE vendor, version), Value: All CPEs that are of (vendor, version)
    vendors_: Set[str]

    def __init__(self, match_threshold: int = 80, n_max_matches: int = 10):
        self.match_threshold = match_threshold
        self.n_max_matches = n_max_matches

    def fit(self, X: List[CPE], y: List[str] = None):
        self.build_lookup_structures(X)
        return self

    @staticmethod
    def filter_short_cpes(cpes: List[CPE]):
        return list(filter(lambda x: len(x.item_name) > 3, cpes))

    def build_lookup_structures(self, X: List[CPE]):
        sufficiently_long_cpes = self.filter_short_cpes(X)
        self.vendor_to_versions_ = {x.vendor: set() for x in sufficiently_long_cpes}
        self.vendors_ = set(self.vendor_to_versions_.keys())
        self.vendor_version_to_cpe_ = dict()

        for cpe in tqdm.tqdm(sufficiently_long_cpes, desc='Fitting the CPE classifier'):
            self.vendor_to_versions_[cpe.vendor].add(cpe.version)
            if (cpe.vendor, cpe.version) not in self.vendor_version_to_cpe_:
                self.vendor_version_to_cpe_[(cpe.vendor, cpe.version)] = {cpe}
            else:
                self.vendor_version_to_cpe_[(cpe.vendor, cpe.version)].add(cpe)

    def predict(self, X: List[Tuple[str, str, str]]) -> List[Optional[List[str]]]:
        """
        Will predict CPE uris for List of Tuples (vendor, product name, identified versions in product name)
        @param X: tuples (vendor, product name, identified versions in product name)
        @return: List of CPE uris that correspond to given input, None if nothing was found.
        """
        return [self.predict_single_cert(x[0], x[1], x[2]) for x in tqdm.tqdm(X, desc='Predicting')]

    def predict_single_cert(self, vendor: str, product_name: str, versions: Optional[List[str]], relax_version: bool = True) -> Optional[List[str]]:
        sanitized_vendor = CPEClassifier._discard_trademark_symbols(vendor).lower() if vendor else vendor
        sanitized_product_name = CPEClassifier._fully_sanitize_string(product_name) if product_name else product_name
        candidate_vendors = self.get_candidate_list_of_vendors(sanitized_vendor)

        candidates = self.get_candidate_cpe_matches(candidate_vendors, versions)
        ratings = [self.compute_best_match(cpe, sanitized_product_name, candidate_vendors, versions) for cpe in candidates]
        threshold = self.match_threshold if not relax_version else 100
        final_matches = list(filter(lambda x: x[0] >= threshold, zip(ratings, candidates)))

        if relax_version and not final_matches:
            return self.predict_single_cert(vendor, product_name, ['-'], relax_version=False)

        return [x[1].uri for x in final_matches[:self.n_max_matches]] if final_matches else None

    def compute_best_match(self, cpe: CPE, product_name: str, candidate_vendors: str, versions: Optional[List[str]]) -> float:
        sanitized_title = CPEClassifier._fully_sanitize_string(cpe.title) if cpe.title else CPEClassifier._fully_sanitize_string(cpe.vendor + ' ' + cpe.item_name + ' ' + cpe.version)
        sanitized_item_name = CPEClassifier._fully_sanitize_string(cpe.item_name)
        cert_stripped = CPEClassifier._strip_manufacturer_and_version(product_name, candidate_vendors, versions)

        token_set_ratio_on_title = fuzz.token_set_ratio(product_name, sanitized_title)
        token_set_ratio_on_item_name = fuzz.token_set_ratio(cert_stripped, sanitized_item_name)
        partial_ratio_on_title = fuzz.partial_ratio(product_name, sanitized_title)
        partial_ratio_on_item_name = fuzz.partial_ratio(cert_stripped, sanitized_item_name)
        return max([token_set_ratio_on_title, partial_ratio_on_title, token_set_ratio_on_item_name, partial_ratio_on_item_name])

    @staticmethod
    def _fully_sanitize_string(string: str) -> str:
        return CPEClassifier._replace_special_chars_with_space(CPEClassifier._discard_trademark_symbols(string.lower()))

    @staticmethod
    def _replace_special_chars_with_space(string: str) -> str:
        replace_non_letter_non_numbers_with_space = re.compile(r"(?ui)\W")
        return replace_non_letter_non_numbers_with_space.sub(' ', string)

    @staticmethod
    def _discard_trademark_symbols(string: str) -> str:
        return string.replace('®', '').replace('™', '')

    @staticmethod
    def _strip_manufacturer_and_version(string: str, manufacturers: List[str], versions: List[str]) -> str:
        for x in manufacturers + versions:
            string = string.lower().replace(CPEClassifier._replace_special_chars_with_space(x.lower()), '').strip()
        return string

    def get_candidate_list_of_vendors(self, manufacturer: str) -> Optional[List[str]]:
        if not manufacturer:
            return None

        result = set()
        splits = re.compile(r'[,/]').findall(manufacturer)

        if splits:
            vendor_tokens = set(itertools.chain.from_iterable([[x.strip() for x in manufacturer.split(s)] for s in splits]))
            result = [self.get_candidate_list_of_vendors(x) for x in vendor_tokens]
            result = list(set(itertools.chain.from_iterable([x for x in result if x])))
            return result if result else None

        if manufacturer in self.vendors_:
            result.add(manufacturer)

        tokenized = manufacturer.split()
        if tokenized[0] in self.vendors_:
            result.add(tokenized[0])
        if len(tokenized) > 1 and tokenized[0] + tokenized[1] in self.vendors_:
            result.add(tokenized[0] + tokenized[1])

        # Below are completely manual fixes
        if 'hewlett' in tokenized or 'hewlett-packard' in tokenized or manufacturer == 'hewlett packard':
            result.add('hp')
        if 'thales' in tokenized:
            result.add('thalesesecurity')
            result.add('thalesgroup')
        if 'stmicroelectronics' in tokenized:
            result.add('st')
        if 'athena' in tokenized and 'smartcard' in tokenized:
            result.add('athena-scs')
        if tokenized[0] == 'the' and not result:
            result = self.get_candidate_list_of_vendors(' '.join(tokenized[1:]))

        return list(result) if result else None

    def get_candidate_vendor_version_pairs(self, cert_candidate_cpe_vendors: List[str], cert_candidate_versions: List[str]) -> Optional[List[Tuple[str, str]]]:
        """
        Given parameters, will return Pairs (cpe_vendor, cpe_version) that are relevant to a given sample
        @param cert_candidate_cpe_vendors: list of CPE vendors relevant to a sample
        @param cert_candidate_versions: List of versions heuristically extracted from the sample name
        @return: List of tuples (cpe_vendor, cpe_version) that can be used in the lookup table to search the CPE dataset.
        """

        def is_cpe_version_among_cert_versions(cpe_version: str, cert_versions: List[str]) -> bool:
            just_numbers = r'(\d{1,5})(\.\d{1,5})' # TODO: The use of this should be double-checked
            for v in cert_versions:
                if (v.startswith(cpe_version) and re.search(just_numbers, cpe_version)) or cpe_version.startswith(v):
                    return True
            return False

        if not cert_candidate_cpe_vendors:
            return None

        candidate_vendor_version_pairs: List[Tuple[str, str]] = []
        for vendor in cert_candidate_cpe_vendors:
            viable_cpe_versions = self.vendor_to_versions_[vendor]
            matched_cpe_versions = [x for x in viable_cpe_versions if is_cpe_version_among_cert_versions(x, cert_candidate_versions)]
            candidate_vendor_version_pairs.extend([(vendor, x) for x in matched_cpe_versions])
        return candidate_vendor_version_pairs

    def new_get_candidate_vendor_version_pairs(self, cert_cpe_vendors, cert_versions):
        if not cert_cpe_vendors:
            return None

        candidate_vendor_version_pairs = []
        for vendor in cert_cpe_vendors:
            viable_cpe_versions = {parse(x) for x in self.vendor_to_versions_[vendor]}
            intersection = viable_cpe_versions.intersection({parse(x) for x in cert_versions})
            candidate_vendor_version_pairs.extend([(vendor, str(x)) for x in intersection])
        return candidate_vendor_version_pairs

    def get_candidate_cpe_matches(self, candidate_vendors: List[str], candidate_versions: List[str]):
        """
        Given List of candidate vendors and candidate versions found in certificate, candidate CPE matches are found
        @param candidate_vendors: List of version strings that were found in the certificate
        @param candidate_versions: List of vendor strings that were found in the certificate
        @return:
        """
        candidate_vendor_version_pairs = self.get_candidate_vendor_version_pairs(candidate_vendors, candidate_versions)
        return list(itertools.chain.from_iterable([self.vendor_version_to_cpe_[x] for x in candidate_vendor_version_pairs])) if candidate_vendor_version_pairs else []
