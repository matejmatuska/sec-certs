# Sec-certs

![](docs/_static/logo.svg)

A tool for data scraping and analysis of security certificates from Common Criteria and FIPS 140-2/3 frameworks. This project is developed by the [Centre for Research On Cryptography and Security](https://crocs.fi.muni.cz) at Masaryk University, Czech Republic.

[![Website](https://img.shields.io/website?down_color=red&down_message=offline&style=flat-square&up_color=SpringGreen&up_message=online&url=https%3A%2F%2Fseccerts.org)](https://seccerts.org)
[![Website](https://img.shields.io/website?down_color=red&down_message=offline&style=flat-square&up_color=SpringGreen&up_message=online&url=https%3A%2F%2Fseccerts.org/docs/index.html)](https://seccerts.org/docs/index.html)
[![PyPI](https://img.shields.io/pypi/v/sec-certs?style=flat-square)](https://pypi.org/project/sec-certs/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/sec-certs?label=Python%20versions&style=flat-square)](https://pypi.org/project/sec-certs/)
[![GitHub Workflow Status](https://img.shields.io/github/workflow/status/crocs-muni/sec-certs/tests?style=flat-square)](https://github.com/crocs-muni/sec-certs/actions/workflows/tests.yml)
[![GitHub Workflow Status](https://img.shields.io/github/workflow/status/crocs-muni/sec-certs/Docker%20Image%20CI?label=Docker%20build&style=flat-square)](https://hub.docker.com/repository/docker/seccerts/sec-certs)

## Installation

Use Docker with `docker pull seccerts/sec-certs` or just `pip install -U sec-certs`. For more elaborate description, see [docs](https://seccerts.org/docs/installation.html).

## Usage

There are two main steps in exploring the world of security certificates:

1. Data scraping and data processing all the certificates
2. Exploring and analysing the processed data

For the first step, we currently provide CLI and our already processed fresh snapshot. For the second step, we provide simple API that can be used directly inside our Jupyter notebook or locally, at your machine.

More elaborate usage is described in [docs/quickstart](https://seccerts.org/docs/quickstart.html). Also, see [example notebooks](https://github.com/crocs-muni/sec-certs/tree/main/notebooks/examples) either at GitHub or at docs. From docs, you can also run our notebooks in Binder.

## Data scraping

Run `sec-certs cc all` for Common Criteria processing, `sec-certs fips all` for FIPS 140 processing.

## Data analysis

Without needing to run the whole processing pipeline, you can fetch fresh snapshot of the dataset and explore it yourself.

```python
dset = CCDataset.from_web_latest()

# Get certificates with some CVE
vulnerable_certs = [x for x in dset if x.heuristics.related_cves]
df_vulnerable = df.loc[~df.related_cves.isna()]

# Show CVE ids of some vulnerable certificate
print(f"{vulnerable_certs[0].heuristics.related_cves=}")

# Get certificates from 2015 and newer
df_2015_and_newer = df.loc[df.year_from > 2014]

# Plot distribution of years of certification
df.year_from.value_counts().sort_index().plot.line()
```

### Explore data with MyBinder Jupyter notebook

Most probably, you don't want to process fresh snapshot of Common Criteria certificates by yourself. Instead, you can use our results and explore them using [online Jupyter notebook](https://mybinder.org/v2/gh/crocs-muni/sec-certs/dev?filepath=notebooks%2Fcpe_cve.ipynb).

### Explore the latest snapshot locally

In Python, run

```python
from sec_certs.dataset.common_criteria import CCDataset
import pandas as pd

dset = CCDataset.from_web_latest()  # now you can inspect the object, certificates are held in dset.certs
df = dset.to_pandas()  # Or you can transform the object into Pandas dataframe
dset.to_json(
    './latest_cc_snapshot.json')  # You may want to store the snapshot as json, so that you don't have to download it again
dset = CCDataset.from_json('./latest_cc_snapshot.json')  # you can now load your stored dataset again
```
