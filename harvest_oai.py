#!/usr/bin/env python3
"""Harvest all documents from an OAI-PMH endpoint and save merged XML output."""

from __future__ import annotations

import argparse
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


OAI_NAMESPACE = "http://www.openarchives.org/OAI/2.0/"
METADATA_PREFIX = "oai_dc"



def build_oai_url(base_url: str, verb: str, metadata_prefix: str | None = None, resumption_token: str | None = None) -> str:
    parsed = urllib.parse.urlparse(base_url)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    query["verb"] = [verb]
    if resumption_token is not None:
        query.pop("metadataPrefix", None)
        query["resumptionToken"] = [resumption_token]
    elif metadata_prefix is not None:
        query.pop("resumptionToken", None)
        query["metadataPrefix"] = [metadata_prefix]
    url = urllib.parse.urlunparse(
        parsed._replace(query=urllib.parse.urlencode(query, doseq=True))
    )
    return url


def fetch_xml(url: str) -> ET.Element:
    req = urllib.request.Request(url, headers={"User-Agent": "Python OAI-PMH Harvester"})
    with urllib.request.urlopen(req) as response:
        content = response.read()
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise RuntimeError(f"Failed to parse XML from {url}: {exc}")


def extract_records_and_resumption(root: ET.Element) -> tuple[list[ET.Element], str | None]:
    records = []
    list_records = root.find(f".//{{{OAI_NAMESPACE}}}ListRecords")
    if list_records is None:
        raise RuntimeError("No <ListRecords> element found in response.")

    for record in list_records.findall(f"{{{OAI_NAMESPACE}}}record"):
        records.append(record)

    resumption = list_records.find(f"{{{OAI_NAMESPACE}}}resumptionToken")
    token = None
    if resumption is not None and resumption.text and resumption.text.strip():
        token = resumption.text.strip()
    return records, token


def harvest_records(base_url: str, metadata_prefix: str) -> list[ET.Element]:
    records: list[ET.Element] = []
    token: str | None = None
    first_url = build_oai_url(base_url, "ListRecords", metadata_prefix=metadata_prefix)
    print(f"Fetching initial batch from: {first_url}")
    response_xml = fetch_xml(first_url)
    batch_records, token = extract_records_and_resumption(response_xml)
    records.extend(batch_records)
    print(f"Collected {len(batch_records)} records, resumptionToken={token!r}")

    while token:
        next_url = build_oai_url(base_url, "ListRecords", resumption_token=token)
        print(f"Fetching next batch from: {next_url}")
        response_xml = fetch_xml(next_url)
        batch_records, token = extract_records_and_resumption(response_xml)
        records.extend(batch_records)
        print(f"Total records collected: {len(records)}, next token={token!r}")

    return records


def write_output(records: list[ET.Element], output_path: str, base_url: str) -> None:
    ET.register_namespace("oai", OAI_NAMESPACE)
    ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")
    ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")

    root = ET.Element(f"{{{OAI_NAMESPACE}}}OAI-PMH")
    request_elem = ET.SubElement(root, f"{{{OAI_NAMESPACE}}}request", verb="ListRecords", metadataPrefix=METADATA_PREFIX)
    request_elem.text = base_url
    list_records = ET.SubElement(root, f"{{{OAI_NAMESPACE}}}ListRecords")

    for record in records:
        list_records.append(record)

    tree = ET.ElementTree(root)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    print(f"Saved merged XML with {len(records)} records to {output_path}")

# cd /d r:\DEV\sustaingain\sustaingain & "C:/Program Files (x86)/Microsoft Visual Studio/Shared/Python37_64/python.exe" harvest_oai.py https://opus4.kobv.de/opus4-hs-augsburg/oai output.xml
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest all OAI-PMH records from an endpoint and save merged XML.")
    parser.add_argument("--base_url", default="https://opus4.kobv.de/opus4-hs-augsburg/oai", help="OAI-PMH base URL, e.g. https://opus4.kobv.de/opus4-hs-augsburg/oai")
    parser.add_argument("--output", default="tha-oai.xml", help="Output XML file path")
    parser.add_argument("--metadata-prefix", default=METADATA_PREFIX, help="metadataPrefix to request (default: oai_dc)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        records = harvest_records(args.base_url, args.metadata_prefix)
        if not records:
            print("No records were returned by the OAI-PMH endpoint.")
            return 1
        write_output(records, args.output, args.base_url)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
