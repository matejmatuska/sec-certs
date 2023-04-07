from __future__ import annotations

from pathlib import Path

import pytest
import tests.data.fips.dataset
from dateutil.parser import isoparse

from sec_certs.dataset import CPEDataset, CVEDataset
from sec_certs.dataset.fips import FIPSDataset
from sec_certs.sample.cpe import CPE, CPEConfiguration
from sec_certs.sample.cve import CVE


@pytest.fixture(scope="module")
def data_dir() -> Path:
    return Path(tests.data.fips.dataset.__path__[0])


@pytest.fixture(scope="module")
def vulnerable_cpe() -> CPE:
    return CPE("cpe:2.3:o:redhat:enterprise_linux:7.1:*:*:*:*:*:*:*", "Red Hat Enterprise Linux 7.1")


@pytest.fixture(scope="module")
def some_random_cpe() -> CPE:
    return CPE(
        "cpe:2.3:a:ibm:security_key_lifecycle_manager:2.6.0.1:*:*:*:*:*:*:*",
        "IBM Security Key Lifecycle Manager 2.6.0.1",
    )


@pytest.fixture(scope="module")
def cve(vulnerable_cpe: CPE) -> CVE:
    return CVE(
        "CVE-1234-123456",
        [vulnerable_cpe],
        [],
        CVE.Metrics(10, "HIGH", 10, 10),
        isoparse("2021-05-26T04:15Z"),
        {"CWE-200"},
    )


@pytest.fixture(scope="module")
def some_other_cve(some_random_cpe: CPE) -> CVE:
    return CVE(
        "CVE-2019-4513",
        [some_random_cpe],
        [],
        CVE.Metrics(8.2, "HIGH", 3.9, 4.2),
        isoparse("2000-05-26T04:15Z"),
        {"CVE-611"},
    )


@pytest.fixture(scope="module")
def ibm_cpe_configuration() -> CPEConfiguration:
    return CPEConfiguration(
        CPE("cpe:2.3:o:ibm:zos:*:*:*:*:*:*:*:*"),
        [
            CPE("cpe:2.3:a:ibm:websphere_application_server:7.0.0.1:*:*:*:*:*:*:*"),
            CPE("cpe:2.3:a:ibm:websphere_application_server:7.0:*:*:*:*:*:*:*"),
            CPE("cpe:2.3:a:ibm:websphere_application_server:7.0.0.2:*:*:*:*:*:*:*"),
            CPE("cpe:2.3:a:ibm:websphere_application_server:7.0.0.3:*:*:*:*:*:*:*"),
            CPE("cpe:2.3:a:ibm:websphere_application_server:7.0.0.4:*:*:*:*:*:*:*"),
            CPE("cpe:2.3:a:ibm:websphere_application_server:7.0.0.5:*:*:*:*:*:*:*"),
            CPE("cpe:2.3:a:ibm:websphere_application_server:7.0.0.6:*:*:*:*:*:*:*"),
            CPE("cpe:2.3:a:ibm:websphere_application_server:7.0.0.7:*:*:*:*:*:*:*"),
            CPE("cpe:2.3:a:ibm:websphere_application_server:7.0.0.8:*:*:*:*:*:*:*"),
            CPE("cpe:2.3:a:ibm:websphere_application_server:7.0.0.9:*:*:*:*:*:*:*"),
            CPE("cpe:2.3:a:ibm:websphere_application_server:*:*:*:*:*:*:*:*"),
        ],
    )


@pytest.fixture(scope="module")
def cpes_ibm_websphere_app_with_platform() -> set[CPE]:
    return {
        CPE("cpe:2.3:o:ibm:zos:*:*:*:*:*:*:*:*", "IBM zOS"),
        CPE("cpe:2.3:a:ibm:websphere_application_server:*:*:*:*:*:*:*:*", "IBM WebSphere Application Server"),
    }


@pytest.fixture(scope="module")
def ibm_xss_cve(ibm_cpe_configuration: CPEConfiguration) -> CVE:
    return CVE(
        "CVE-2010-2325",
        [],
        [ibm_cpe_configuration],
        CVE.Metrics(4.3, "MEDIUM", 2.9, 8.6),
        isoparse("2000-06-18T04:15Z"),
        {"CWE-79"},
    )


@pytest.fixture(scope="module")
def cpe_dataset(
    vulnerable_cpe: CPE, some_random_cpe: CPE, cpes_ibm_websphere_app_with_platform: set[CPE]
) -> CPEDataset:
    cpes = {
        vulnerable_cpe,
        some_random_cpe,
        CPE(
            "cpe:2.3:a:semperplugins:all_in_one_seo_pack:1.3.6.4:*:*:*:*:wordpress:*:*",
            "Semper Plugins All in One SEO Pack 1.3.6.4 for WordPress",
        ),
        CPE(
            "cpe:2.3:a:tracker-software:pdf-xchange_lite_printer:6.0.320.0:*:*:*:*:*:*:*",
            "Tracker Software PDF-XChange Lite Printer 6.0.320.0",
        ),
        *cpes_ibm_websphere_app_with_platform,
    }

    return CPEDataset(False, {x.uri: x for x in cpes})


@pytest.fixture(scope="module")
def cve_dataset(cve: CVE, some_other_cve: CVE, ibm_xss_cve: CVE) -> CVEDataset:
    cves = {cve, some_other_cve, ibm_xss_cve}
    cve_dset = CVEDataset({x.cve_id: x for x in cves})
    cve_dset.build_lookup_dict(use_nist_mapping=False)
    return cve_dset


@pytest.fixture(scope="module")
def toy_static_dataset(data_dir: Path) -> FIPSDataset:
    return FIPSDataset.from_json(data_dir / "toy_dataset.json")


@pytest.fixture(scope="module")
def processed_dataset(
    toy_static_dataset: FIPSDataset, cpe_dataset: CPEDataset, cve_dataset: CVEDataset, tmp_path_factory
) -> FIPSDataset:
    tmp_dir = tmp_path_factory.mktemp("fips_dset")
    toy_static_dataset.copy_dataset(tmp_dir)

    tested_certs = [
        toy_static_dataset["3095"],
        toy_static_dataset["3093"],
        toy_static_dataset["3197"],
        toy_static_dataset["2441"],
    ]
    toy_static_dataset.certs = {x.dgst: x for x in tested_certs}

    toy_static_dataset.download_all_artifacts()
    toy_static_dataset.convert_all_pdfs()
    toy_static_dataset.extract_data()
    toy_static_dataset._compute_references(keep_unknowns=True)

    toy_static_dataset.auxiliary_datasets.cpe_dset = cpe_dataset
    toy_static_dataset.auxiliary_datasets.cve_dset = cve_dataset
    toy_static_dataset.compute_cpe_heuristics()
    toy_static_dataset.compute_related_cves()
    toy_static_dataset._compute_transitive_vulnerabilities()

    return toy_static_dataset


@pytest.mark.parametrize(
    "input_dgst, expected_refs",
    [
        ("3095", {"3093", "3094", "3096"}),
        ("3093", {"3090", "3091"}),
        ("3197", {"3195", "3096", "3196", "3644", "3651"}),
    ],
)
def test_html_modules_directly_referencing(processed_dataset: FIPSDataset, input_dgst: str, expected_refs: set[str]):
    crt = processed_dataset[input_dgst]
    if not crt.state.module_extract_ok:
        pytest.xfail(reason="Data from module not extracted")
    assert crt.heuristics.module_processed_references.directly_referencing == expected_refs


@pytest.mark.parametrize("input_dgst, expected_refs", [("3095", {"3093", "3094", "3096"}), ("3093", {"3090", "3091"})])
def test_pdf_policies_directly_referencing(processed_dataset: FIPSDataset, input_dgst: str, expected_refs: set[str]):
    crt = processed_dataset[input_dgst]
    if not crt.state.policy_extract_ok:
        pytest.xfail(reason="Data from policy not extracted")
    assert crt.heuristics.policy_processed_references.directly_referencing == expected_refs


@pytest.mark.parametrize(
    "input_dgst, expected_refs",
    [
        (
            "3093",
            {
                "3090",
                "3091",
            },
        ),
        ("3095", {"3090", "3091", "3093", "3094", "3096"}),
    ],
)
def test_html_modules_indirectly_referencing(processed_dataset: FIPSDataset, input_dgst: str, expected_refs: set[str]):
    crt = processed_dataset[input_dgst]
    if not crt.state.module_extract_ok:
        pytest.xfail(reason="Data from module not extracted")
    assert crt.heuristics.module_processed_references.indirectly_referencing == expected_refs


@pytest.mark.parametrize(
    "input_dgst, expected_refs",
    [("3095", {"3090", "3091", "3093", "3094", "3096"}), ("3093", {"3090", "3091"})],
)
def test_pdf_policies_indirectly_referencing(processed_dataset: FIPSDataset, input_dgst: str, expected_refs: set[str]):
    crt = processed_dataset[input_dgst]
    if not crt.state.policy_extract_ok:
        pytest.xfail(reason="Data from policy not extracted")
    assert crt.heuristics.policy_processed_references.indirectly_referencing == expected_refs


@pytest.mark.parametrize("input_dgst, expected_refs", [("3095", None), ("3093", {"3095"})])
def test_html_modules_directly_referenced_by(
    processed_dataset: FIPSDataset, input_dgst: str, expected_refs: set[str] | None
):
    crt = processed_dataset[input_dgst]
    if not crt.state.module_extract_ok:
        pytest.xfail(reason="Data from module not extracted")
    assert crt.heuristics.module_processed_references.directly_referenced_by == expected_refs


@pytest.mark.parametrize("input_dgst, expected_refs", [("3095", None), ("3093", {"3095"})])
def test_pdf_policies_directly_referenced_by(
    processed_dataset: FIPSDataset, input_dgst: str, expected_refs: set[str] | None
):
    crt = processed_dataset[input_dgst]
    if not crt.state.policy_extract_ok:
        pytest.xfail(reason="Data from policy not extracted")
    assert crt.heuristics.policy_processed_references.directly_referenced_by == expected_refs


@pytest.mark.parametrize("input_dgst, expected_refs", [("3095", None), ("3093", {"3095"})])
def test_html_modules_indirectly_referenced_by(
    processed_dataset: FIPSDataset, input_dgst: str, expected_refs: set[str] | None
):
    crt = processed_dataset[input_dgst]
    if not crt.state.module_extract_ok:
        pytest.xfail(reason="Data from module not extracted")
    assert crt.heuristics.module_processed_references.indirectly_referenced_by == expected_refs


@pytest.mark.parametrize("input_dgst, expected_refs", [("3095", None), ("3093", {"3095"})])
def test_pdf_policies_indirectly_referenced_by(
    processed_dataset: FIPSDataset, input_dgst: str, expected_refs: set[str] | None
):
    crt = processed_dataset[input_dgst]
    if not crt.state.policy_extract_ok:
        pytest.xfail(reason="Data from module not extracted")
    assert crt.heuristics.module_processed_references.indirectly_referenced_by == expected_refs


def test_match_cpe(processed_dataset: FIPSDataset, vulnerable_cpe: CPE, some_random_cpe: CPE):
    assert processed_dataset["2441"].heuristics.cpe_matches
    assert vulnerable_cpe.uri in processed_dataset["2441"].heuristics.cpe_matches
    assert some_random_cpe.uri not in processed_dataset["2441"].heuristics.cpe_matches


def test_find_related_cves(processed_dataset: FIPSDataset, cve: CVE, some_other_cve: CVE):
    assert processed_dataset["2441"].heuristics.related_cves
    assert cve.cve_id in processed_dataset["2441"].heuristics.related_cves
    assert some_other_cve not in processed_dataset["2441"].heuristics.related_cves


def test_find_related_cves_for_cpe_configuration(
    processed_dataset: FIPSDataset,
    cve_dataset: CVEDataset,
    ibm_xss_cve: CVE,
    cpes_ibm_websphere_app_with_platform: set[CPE],
):
    cve_dataset.cves = {ibm_xss_cve.cve_id: ibm_xss_cve}
    cert = processed_dataset["2441"]
    cert.heuristics.cpe_matches = {cpe.uri for cpe in cpes_ibm_websphere_app_with_platform}
    processed_dataset.auxiliary_datasets.cve_dset = cve_dataset
    processed_dataset.compute_related_cves()
    assert cert.heuristics.related_cves == {ibm_xss_cve.cve_id}


def test_keywords_heuristics(processed_dataset: FIPSDataset):
    keywords = processed_dataset["2441"].pdf_data.keywords
    assert keywords
    assert keywords["symmetric_crypto"]["AES_competition"]["AES"]["AES"] == 53
    assert not keywords["pq_crypto"]
    assert keywords["crypto_library"]["OpenSSL"]["OpenSSL"] == 83
    assert keywords["side_channel_analysis"]["SCA"]["timing attacks"] == 1
