from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from io import BytesIO
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String

from app.schemas import AssessmentResponse, CitedStatement, Coordinates, GaugeReading


class PdfIncidentReportGenerator:
    """Creates a source-traceable operational PDF from a completed assessment."""

    def __init__(self) -> None:
        styles = getSampleStyleSheet()
        self._styles = {
            "title": ParagraphStyle(
                "AegisTitle",
                parent=styles["Title"],
                fontName="Helvetica-Bold",
                fontSize=20,
                leading=24,
                textColor=colors.HexColor("#173b5b"),
                spaceAfter=4,
            ),
            "subtitle": ParagraphStyle(
                "AegisSubtitle",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#4e6675"),
                spaceAfter=14,
            ),
            "heading": ParagraphStyle(
                "AegisHeading",
                parent=styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=12,
                leading=15,
                textColor=colors.HexColor("#173b5b"),
                spaceBefore=14,
                spaceAfter=7,
            ),
            "body": ParagraphStyle(
                "AegisBody",
                parent=styles["BodyText"],
                fontName="Helvetica",
                fontSize=9,
                leading=13,
                spaceAfter=5,
            ),
            "small": ParagraphStyle(
                "AegisSmall",
                parent=styles["BodyText"],
                fontName="Helvetica",
                fontSize=7.5,
                leading=10,
                textColor=colors.HexColor("#4e6675"),
            ),
            "label": ParagraphStyle(
                "AegisLabel",
                parent=styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=8,
                leading=10,
                textColor=colors.HexColor("#294c60"),
            ),
        }

    def generate(self, assessment: AssessmentResponse) -> bytes:
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=LETTER,
            leftMargin=0.65 * inch,
            rightMargin=0.65 * inch,
            topMargin=0.62 * inch,
            bottomMargin=0.62 * inch,
            title=f"Aegis Incident Report {assessment.assessment_id}",
            author="Aegis Operations",
        )
        story = self._build_story(assessment)
        document.build(
            story,
            onFirstPage=self._draw_footer,
            onLaterPages=self._draw_footer,
        )
        return buffer.getvalue()

    def _build_story(self, assessment: AssessmentResponse) -> list[Flowable]:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        report_title = "AEGIS INCIDENT REPORT"
        if assessment.demo_scenario:
            report_title += " - DEMONSTRATION"
        story: list[Flowable] = [
            Paragraph(report_title, self._styles["title"]),
            Paragraph(
                "Decision-support report for infrastructure and emergency-management review. "
                "Not an official FEMA, DOT, evacuation, closure, or dispatch order.",
                self._styles["subtitle"],
            ),
            self._risk_banner(assessment),
            self._heading("Incident Overview"),
            self._table(
                [
                    ("Incident ID", assessment.assessment_id),
                    ("Generated", generated_at),
                    ("Asset", self._asset_name(assessment)),
                    ("Location", self._location(assessment)),
                    ("Condition score", f"{assessment.asset.condition_score}/100"),
                    ("Asset age", f"{assessment.asset.age_years} years"),
                    ("Observed scour", "Yes" if assessment.asset.observed_scour else "No"),
                    ("Emergency access", "Confirmed" if assessment.asset.emergency_access_route else "Not confirmed"),
                    ("Workflow status", assessment.status.replace("_", " ").title()),
                    ("Review status", "Human approval required"),
                ]
            ),
            *self._official_bridge_section(assessment),
            self._heading("Bridge and Risk Analysis"),
            self._table(
                [
                    ("Composite risk", assessment.risk.risk_level.value),
                    ("Risk score", f"{assessment.risk.score}/100"),
                    ("Model confidence", f"{assessment.risk.confidence}%"),
                    ("Assessment basis", " ".join(assessment.risk.reasons)),
                ]
            ),
            KeepTogether(
                [self._heading("Weather and Flood Intelligence"), self._weather_flood_table(assessment)]
            ),
            self._heading("Operational Map"),
            self._operational_map(assessment),
            Paragraph(
                "Vector operational overview generated from the assessment evidence. It is not a survey, "
                "official flood map, or navigational product.",
                self._styles["small"],
            ),
            self._heading("Alternative Route and Nearby Infrastructure"),
            self._route_and_infrastructure(assessment),
            self._agent_workflow_summary(assessment),
            self._heading("AI Incident Commander"),
            *self._commander_section(assessment),
            KeepTogether(
                [self._heading("Data Sources and Known Gaps"), *self._sources_section(assessment)]
            ),
        ]
        return story

    def _official_bridge_section(self, assessment: AssessmentResponse) -> list[Flowable]:
        bridge = assessment.official_bridge
        if bridge is None:
            return []
        traffic = (
            f"{bridge.average_daily_traffic:,} vehicles/day"
            + (f" ({bridge.traffic_year})" if bridge.traffic_year else "")
            if bridge.average_daily_traffic is not None
            else "Not provided"
        )
        return [
            self._heading("Official Bridge Record"),
            self._table(
                [
                    ("Source", "FHWA National Bridge Inventory"),
                    ("NBI record ID", bridge.nbi_record_id),
                    ("Verified coordinates", f"{bridge.coordinates.latitude:.6f}, {bridge.coordinates.longitude:.6f}"),
                    ("Route", bridge.route or "Not provided"),
                    ("Inventory location", bridge.location_description or "Not provided"),
                    ("Year built", str(bridge.year_built) if bridge.year_built else "Not provided"),
                    ("NBI component score", f"{bridge.condition_score}/100" if bridge.condition_score is not None else "Not provided"),
                    ("Traffic", traffic),
                    ("Last inspection", bridge.last_inspection_date or "Not provided"),
                    ("Dataset", bridge.data_as_of or "Not provided"),
                ]
            ),
            Paragraph(" ".join(bridge.limitations), self._styles["small"]),
        ]

    def _risk_banner(self, assessment: AssessmentResponse) -> Table:
        color = {
            "LOW": "#2d7a5e",
            "MODERATE": "#b17925",
            "HIGH": "#c86a20",
            "CRITICAL": "#a83f36",
        }[assessment.risk.risk_level.value]
        content = [
            [
                Paragraph("CURRENT ASSESSMENT", self._styles["label"]),
                Paragraph(
                    f"<b>{escape(assessment.risk.risk_level.value)}</b>  |  "
                    f"Score {assessment.risk.score}/100  |  Confidence {assessment.risk.confidence}%",
                    ParagraphStyle(
                        "RiskBanner",
                        parent=self._styles["body"],
                        textColor=colors.white,
                        fontSize=11,
                        leading=14,
                    ),
                ),
            ]
        ]
        table = Table(content, colWidths=[1.45 * inch, 5.15 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#e8eef2")),
                    ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(color)),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ]
            )
        )
        return table

    def _weather_flood_table(self, assessment: AssessmentResponse) -> Table:
        live = assessment.live_intelligence
        weather = live.weather if live else None
        flood = live.flood_forecast if live else None
        gauge = live.nearest_gauge if live else None
        alerts = live.weather_alerts if live else []
        rows = [
            (
                "Weather forecast",
                (
                    f"{weather.precipitation_next_24h_mm:.1f} mm precipitation and "
                    f"{weather.wind_gust_kph:.1f} km/h peak gusts over the next 24 hours."
                    if weather
                    else "Unavailable; manual values remained in the risk assessment."
                ),
            ),
            (
                "Flood forecast",
                (
                    f"Current modelled discharge {flood.river_discharge_m3s:.1f} m3/s; "
                    f"seven-day peak {flood.peak_7day_discharge_m3s:.1f} m3/s."
                    if flood
                    else "Unavailable."
                ),
            ),
            (
                "River observation",
                self._gauge_text(gauge),
            ),
            (
                "Official alerts",
                "; ".join(alert.event for alert in alerts[:4]) if alerts else "No active alerts returned or source unavailable.",
            ),
            (
                "Terrain context",
                (
                    f"Asset elevation: {live.terrain.elevation_meters:.1f} m."
                    if live and live.terrain
                    else "Unavailable."
                ),
            ),
        ]
        return self._table(rows)

    def _operational_map(self, assessment: AssessmentResponse) -> Flowable:
        live = assessment.live_intelligence
        if not live or not live.coordinates:
            return Paragraph("No resolved coordinates were available for the operational map.", self._styles["body"])

        drawing = Drawing(500, 210)
        drawing.add(Rect(0, 0, 500, 210, fillColor=colors.HexColor("#edf3f5"), strokeColor=colors.HexColor("#b9c9d0")))
        for offset in range(40, 500, 60):
            drawing.add(Line(offset, 0, offset, 210, strokeColor=colors.HexColor("#dbe5e9"), strokeWidth=0.4))
        for offset in range(35, 210, 50):
            drawing.add(Line(0, offset, 500, offset, strokeColor=colors.HexColor("#dbe5e9"), strokeWidth=0.4))

        points = [live.coordinates]
        points.extend(asset.coordinates for asset in live.bridge_assets[:30])
        points.extend(facility.coordinates for facility in live.critical_infrastructure[:40])
        if live.alternate_route:
            points.extend(live.alternate_route.geometry)
        bounds = self._coordinate_bounds(points)
        project = lambda coordinate: self._project(coordinate, bounds, 20, 24, 460, 150)

        if live.flood_screening:
            center_x, center_y = project(live.flood_screening.center)
            lat_span = max(bounds[1] - bounds[0], 0.001)
            radius = min(88, max(12, live.flood_screening.radius_meters / (lat_span * 111_000) * 150))
            drawing.add(Circle(center_x, center_y, radius, fillColor=colors.Color(0.2, 0.45, 0.63, alpha=0.14), strokeColor=colors.HexColor("#3274a1"), strokeWidth=1.2))

        if live.alternate_route and len(live.alternate_route.geometry) > 1:
            route_points = [project(point) for point in live.alternate_route.geometry]
            for start, end in zip(route_points, route_points[1:]):
                drawing.add(Line(start[0], start[1], end[0], end[1], strokeColor=colors.HexColor("#6f5a99"), strokeWidth=2.4))

        for facility in live.critical_infrastructure[:40]:
            x, y = project(facility.coordinates)
            drawing.add(Rect(x - 2.5, y - 2.5, 5, 5, fillColor=colors.HexColor("#4f6574"), strokeColor=None))
        for bridge in live.bridge_assets[1:30]:
            x, y = project(bridge.coordinates)
            drawing.add(Circle(x, y, 2.4, fillColor=colors.HexColor("#00756c"), strokeColor=None))

        asset_x, asset_y = project(live.coordinates)
        risk_color = {
            "LOW": "#2d7a5e",
            "MODERATE": "#b17925",
            "HIGH": "#c86a20",
            "CRITICAL": "#a83f36",
        }[assessment.risk.risk_level.value]
        drawing.add(Circle(asset_x, asset_y, 7, fillColor=colors.HexColor(risk_color), strokeColor=colors.white, strokeWidth=1.4))
        drawing.add(String(20, 187, "OPERATIONAL MAP OVERVIEW", fontName="Helvetica-Bold", fontSize=8, fillColor=colors.HexColor("#294c60")))
        drawing.add(String(20, 9, "Risk asset", fontName="Helvetica", fontSize=7, fillColor=colors.HexColor("#394d58")))
        drawing.add(Circle(13, 11, 3.2, fillColor=colors.HexColor(risk_color), strokeColor=None))
        drawing.add(String(90, 9, "Nearby bridge", fontName="Helvetica", fontSize=7, fillColor=colors.HexColor("#394d58")))
        drawing.add(Circle(83, 11, 2.2, fillColor=colors.HexColor("#00756c"), strokeColor=None))
        drawing.add(String(172, 9, "Critical facility", fontName="Helvetica", fontSize=7, fillColor=colors.HexColor("#394d58")))
        drawing.add(Rect(164, 8.5, 5, 5, fillColor=colors.HexColor("#4f6574"), strokeColor=None))
        drawing.add(String(276, 9, "Suggested route", fontName="Helvetica", fontSize=7, fillColor=colors.HexColor("#394d58")))
        drawing.add(Line(267, 11, 273, 11, strokeColor=colors.HexColor("#6f5a99"), strokeWidth=2))
        return drawing

    def _route_and_infrastructure(self, assessment: AssessmentResponse) -> Flowable:
        live = assessment.live_intelligence
        if not live:
            return Paragraph("No live operating-picture data was available.", self._styles["body"])
        route = live.alternate_route
        route_text = (
            f"{route.label}: {route.distance_km:.1f} km, approximately {route.duration_minutes:.0f} minutes. Planning only."
            if route
            else "No suggested detour was returned."
        )
        categories = self._count_categories(facility.category for facility in live.critical_infrastructure)
        facility_text = ", ".join(f"{count} {name}" for name, count in categories.items()) or "No mapped facilities returned."
        return self._table([("Alternative route", route_text), ("Nearby critical infrastructure", facility_text)])

    def _agent_workflow_summary(self, assessment: AssessmentResponse) -> Flowable:
        complete = sum(finding.status == "complete" for finding in assessment.findings)
        degraded = sum(finding.status == "degraded" for finding in assessment.findings)
        return Paragraph(
            (
                f"<b>Multi-agent workflow:</b> {len(assessment.findings)} outputs recorded; "
                f"{complete} complete, {degraded} degraded. Individual agent details are retained in the digital assessment record."
            ),
            self._styles["small"],
        )

    def _commander_section(self, assessment: AssessmentResponse) -> list[Flowable]:
        commander = assessment.incident_commander
        if not commander:
            return [
                Paragraph("AI Incident Commander was not configured for this assessment.", self._styles["body"]),
                *self._statement_list(
                    [CitedStatement(text=action, source_ids=["aegis-risk-model"]) for action in assessment.risk.recommended_actions],
                    assessment,
                ),
            ]
        availability = "Groq evidence synthesis" if commander.available else "Deterministic source-cited fallback"
        content: list[Flowable] = [
            Paragraph(f"<b>{escape(availability)}.</b> {escape(commander.executive_summary)}", self._styles["body"]),
            Paragraph("Immediate priorities", self._styles["label"]),
            *self._statement_list(commander.immediate_priorities, assessment),
            Paragraph("Recommended actions", self._styles["label"]),
            *self._statement_list(commander.recommended_actions, assessment),
            Paragraph("Long-term recommendations", self._styles["label"]),
            *self._statement_list(commander.long_term_recommendations, assessment),
        ]
        if commander.data_gaps:
            content.append(Paragraph(f"<b>Data gaps:</b> {escape(' '.join(commander.data_gaps))}", self._styles["small"]))
        if commander.warning:
            content.append(Paragraph(f"<b>Commander status:</b> {escape(commander.warning)}", self._styles["small"]))
        return content

    def _sources_section(self, assessment: AssessmentResponse) -> list[Flowable]:
        live = assessment.live_intelligence
        sources = live.sources if live else []
        rows: list[Flowable] = []
        if sources:
            for source in sources:
                detail = f"{source.provider} - {source.label}"
                if source.url:
                    detail += f" ({source.url})"
                rows.append(Paragraph(escape(detail), self._styles["small"]))
        else:
            rows.append(Paragraph("No live external sources were available; the report relies on operator inputs and the deterministic risk model.", self._styles["small"]))
        if live and live.warnings:
            rows.append(Spacer(1, 5))
            rows.append(Paragraph("<b>Known gaps:</b> " + escape(" ".join(live.warnings)), self._styles["small"]))
        return rows

    def _statement_list(
        self, statements: Iterable[CitedStatement], assessment: AssessmentResponse
    ) -> list[Flowable]:
        labels = self._source_labels(assessment)
        items: list[Flowable] = []
        for statement in statements:
            citation = ", ".join(labels.get(source_id, source_id) for source_id in statement.source_ids)
            items.append(
                Paragraph(
                    f"- {escape(statement.text)}<br/><font color='#315f8d' size='7'>Sources: {escape(citation)}</font>",
                    self._styles["body"],
                )
            )
        return items or [Paragraph("No recommendations were generated.", self._styles["body"])]

    @staticmethod
    def _source_labels(assessment: AssessmentResponse) -> dict[str, str]:
        labels = {
            "operator-field-report": "Operator field report",
            "operator-assessment-inputs": "Operator assessment inputs",
            "aegis-risk-model": "Aegis deterministic risk model",
        }
        if assessment.live_intelligence:
            labels.update(
                {source.id: f"{source.provider} - {source.label}" for source in assessment.live_intelligence.sources}
            )
        return labels

    def _table(self, rows: list[tuple[str, str]]) -> Table:
        data = [
            [Paragraph(escape(label), self._styles["label"]), Paragraph(escape(value), self._styles["body"])]
            for label, value in rows
        ]
        table = Table(data, colWidths=[1.45 * inch, 5.15 * inch], repeatRows=0)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf3f5")),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c7d4d9")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    def _heading(self, text: str) -> Paragraph:
        return Paragraph(text, self._styles["heading"])

    @staticmethod
    def _asset_name(assessment: AssessmentResponse) -> str:
        live = assessment.live_intelligence
        if live and live.bridge_assets:
            return live.bridge_assets[0].name
        return assessment.asset.name

    @staticmethod
    def _location(assessment: AssessmentResponse) -> str:
        live = assessment.live_intelligence
        return live.resolved_location if live and live.resolved_location else assessment.asset.location

    @staticmethod
    def _gauge_text(gauge: GaugeReading | None) -> str:
        if gauge is None:
            return "No nearby gauge reading was available."
        if gauge.stage_ft is not None:
            return f"{gauge.site_name}: stage {gauge.stage_ft:.2f} ft."
        if gauge.flow_cfs is not None:
            return f"{gauge.site_name}: flow {gauge.flow_cfs:.0f} cfs."
        return f"{gauge.site_name}: no current stage or flow value returned."

    @staticmethod
    def _count_categories(categories: Iterable[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for category in categories:
            counts[category] = counts.get(category, 0) + 1
        return counts

    @staticmethod
    def _coordinate_bounds(points: list[Coordinates]) -> tuple[float, float, float, float]:
        latitudes = [point.latitude for point in points]
        longitudes = [point.longitude for point in points]
        lat_padding = max((max(latitudes) - min(latitudes)) * 0.12, 0.01)
        lon_padding = max((max(longitudes) - min(longitudes)) * 0.12, 0.01)
        return (
            min(latitudes) - lat_padding,
            max(latitudes) + lat_padding,
            min(longitudes) - lon_padding,
            max(longitudes) + lon_padding,
        )

    @staticmethod
    def _project(
        point: Coordinates,
        bounds: tuple[float, float, float, float],
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> tuple[float, float]:
        min_lat, max_lat, min_lon, max_lon = bounds
        projected_x = x + (point.longitude - min_lon) / max(max_lon - min_lon, 0.0001) * width
        projected_y = y + (point.latitude - min_lat) / max(max_lat - min_lat, 0.0001) * height
        return projected_x, projected_y

    @staticmethod
    def _draw_footer(canvas: object, document: object) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#c7d4d9"))
        canvas.line(document.leftMargin, 0.42 * inch, LETTER[0] - document.rightMargin, 0.42 * inch)
        canvas.setFillColor(colors.HexColor("#4e6675"))
        canvas.setFont("Helvetica", 7)
        canvas.drawString(document.leftMargin, 0.27 * inch, "Aegis Operations | Human review required before action")
        canvas.drawRightString(LETTER[0] - document.rightMargin, 0.27 * inch, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()
