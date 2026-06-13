"""Parser tests against real captured GePNIC and CPPP HTML fragments."""

from __future__ import annotations

from tenderwatch.parsing import (
    parse_cppp_listing,
    parse_gepnic_datetime,
    parse_gepnic_listing,
    parse_msrdc_listing,
    parse_org_directory,
)

MSRDC_HTML = """
<table id="SitePH_grdTendersList">
  <tr><th>&nbsp;</th><th>Sr.No.</th><th>Department Name</th><th>Tender No</th>
    <th>Tender Name</th><th>Publication Date</th><th>Last Submission Date</th>
    <th>File Size(MB)</th><th>View/Download</th></tr>
  <tr><td>1</td><td>Construction</td><td>T 2901</td>
    <td>Widening and strengthening of Samruddhi Mahamarg approach road</td>
    <td>10/06/2026</td><td>28/06/2026</td><td>1.2</td>
    <td><a href="/Site/Upload/Tender/t2901.pdf">Download</a></td></tr>
</table>
"""

ORG_DIRECTORY_HTML = """
<table class="list_table" id="table">
  <tr class="list_header"><td>S.No</td><td>Organisation Name</td><td>Tender Count</td></tr>
  <tr class="even" id="informal_2">
    <td align="left">1</td>
    <td align="left">Ahmednagar Municipal Corporation</td>
    <td align="right"><a id="DirectLink" class="link2"
      href="/nicgep/app?component=%24DirectLink&amp;page=FrontEndTendersByOrganisation&amp;service=direct&amp;session=T&amp;sp=Sdtz14e">1</a></td>
  </tr>
  <tr class="odd" id="informal_3">
    <td align="left">2</td>
    <td align="left">Public Works Region</td>
    <td align="right"><a id="DirectLink_0" class="link2"
      href="/nicgep/app?component=%24DirectLink&amp;sp=SL2">148</a></td>
  </tr>
</table>
"""

GEPNIC_LISTING_HTML = """
<table class="list_table" id="table">
  <tr class="list_header"><td>S.No</td><td>e-Published Date</td><td>Closing Date</td>
    <td>Opening Date</td><td>Title and Ref.No./Tender ID</td><td>Organisation Chain</td></tr>
  <tr class="even" id="informal_2">
    <td align="center">1</td>
    <td align="center">12-Jun-2026 10:00 AM</td>
    <td align="center">17-Jun-2026 10:00 AM</td>
    <td align="center">18-Jun-2026 10:00 AM</td>
    <td align="center"><a id="DirectLink" title="View Tender Information"
      href="/nicgep/app?component=%24DirectLink&amp;sp=SK">[Improvement of CC Road at Ward 7]</a>
      [MDE/E/188][2026_MCGM_1308095_1]</td>
    <td align="center">Municipal Corporation of Greater Mumbai||N Ward||Roads</td>
  </tr>
</table>
"""

CPPP_LISTING_HTML = """
<table><thead><tr><th>Sl.No</th><th>e-Published Date</th>
<th>Bid Submission Closing Date</th><th>Tender Opening Date</th>
<th>Title/Ref.No./Tender Id</th><th>Organisation Name</th><th>Corrigendum</th></tr>
</thead><tbody><tr>
  <td>1.</td>
  <td>12-Jun-2026 10:30 AM</td>
  <td>15-Jun-2026 03:00 PM</td>
  <td>16-Jun-2026 04:00 PM</td>
  <td><a href="https://eprocure.gov.in/cppp/tendersfullview/abc123"
    title="External Url">Construction of approach road to bridge</a>/NTPC/USSC-CPG3/9900327423/2026_NTPC_109041_1</td>
  <td>NTPC Limited</td>
  <td>--</td>
</tr></tbody></table>
"""


def test_parse_gepnic_datetime() -> None:
    assert parse_gepnic_datetime("12-Jun-2026 10:00 AM") == "2026-06-12 10:00"
    assert parse_gepnic_datetime("12-Jun-2026 03:15 PM") == "2026-06-12 15:15"
    assert parse_gepnic_datetime("not a date") is None


def test_parse_org_directory() -> None:
    orgs = parse_org_directory(ORG_DIRECTORY_HTML)
    assert len(orgs) == 2
    assert orgs[0].name == "Ahmednagar Municipal Corporation"
    assert orgs[0].count == 1
    assert orgs[1].count == 148
    assert "DirectLink" in orgs[1].link


def test_parse_gepnic_listing() -> None:
    rows = parse_gepnic_listing(GEPNIC_LISTING_HTML)
    assert len(rows) == 1
    row = rows[0]
    assert row.tender_id == "2026_MCGM_1308095_1"
    assert row.title == "Improvement of CC Road at Ward 7"
    assert row.ref_no == "MDE/E/188"
    assert row.published == "2026-06-12 10:00"
    assert row.closing == "2026-06-17 10:00"
    assert "Greater Mumbai" in row.organisation


def test_parse_msrdc_listing() -> None:
    rows = parse_msrdc_listing(MSRDC_HTML)
    assert len(rows) == 1
    row = rows[0]
    assert "Samruddhi" in row.title
    assert row.ref_no == "T 2901"
    assert row.organisation == "MSRDC - Construction"
    assert row.published == "2026-06-10 00:00"
    assert row.closing == "2026-06-28 23:59"
    assert row.url == "https://msrdc.in/Site/Upload/Tender/t2901.pdf"


def test_parse_cppp_listing() -> None:
    rows = parse_cppp_listing(CPPP_LISTING_HTML)
    assert len(rows) == 1
    row = rows[0]
    assert row.tender_id == "2026_NTPC_109041_1"
    assert row.title == "Construction of approach road to bridge"
    assert row.url is not None and row.url.startswith(
        "https://eprocure.gov.in/cppp/tendersfullview/"
    )
    assert row.organisation == "NTPC Limited"
    assert "9900327423" in row.ref_no
