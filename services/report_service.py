"""
Report generation service.

Produces PDF, Excel, and PowerPoint exports of workforce analytics
data. Each format includes KPIs, charts, tables, and an AI-written
summary.
"""

from __future__ import annotations

import io
import json
import tempfile
from datetime import datetime
from logging import Logger
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from utils.exceptions import ServiceError


class ReportService:
    """
    Generates exported reports in PDF, Excel, and PowerPoint.

    All methods accept a data snapshot (from AnalyticsAgent)
    and return bytes ready for download.
    """

    def __init__(self, logger: Logger) -> None:
        self._logger = logger

    # ----------------------------------------------------------------
    # Excel
    # ----------------------------------------------------------------

    def to_excel(
        self,
        data: Dict[str, Any],
        summary: str = "",
    ) -> bytes:
        """
        Generate an Excel workbook with multiple sheets.

        Args:
            data: Analytics snapshot dict.
            summary: AI-written text summary.

        Returns:
            Excel file as bytes.
        """
        try:
            output = io.BytesIO()

            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                # Overview
                overview = pd.DataFrame(
                    {
                        "Metric": ["Total Employees", "Average Tenure (years)"],
                        "Value": [
                            data.get("total_headcount", 0),
                            data.get("average_tenure_years", 0),
                        ],
                    }
                )
                overview.to_excel(writer, sheet_name="Overview", index=False)

                # Department breakdown
                dept_data = data.get("by_department", [])
                if dept_data:
                    pd.DataFrame(dept_data).to_excel(
                        writer, sheet_name="By Department", index=False,
                    )

                # Status breakdown
                status_data = data.get("by_status", [])
                if status_data:
                    pd.DataFrame(status_data).to_excel(
                        writer, sheet_name="By Status", index=False,
                    )

                # Gender breakdown
                gender_data = data.get("by_gender", [])
                if gender_data:
                    pd.DataFrame(gender_data).to_excel(
                        writer, sheet_name="By Gender", index=False,
                    )

                # Hiring trends
                hiring_year = data.get("hiring_by_year", [])
                if hiring_year:
                    pd.DataFrame(hiring_year).to_excel(
                        writer, sheet_name="Hiring by Year", index=False,
                    )

                hiring_month = data.get("hiring_by_month", [])
                if hiring_month:
                    pd.DataFrame(hiring_month).to_excel(
                        writer, sheet_name="Hiring by Month", index=False,
                    )

                # Tenure distribution
                tenure_data = data.get("tenure_distribution", [])
                if tenure_data:
                    pd.DataFrame(tenure_data).to_excel(
                        writer, sheet_name="Tenure Distribution", index=False,
                    )

                # Summary sheet
                if summary:
                    pd.DataFrame(
                        {"AI Summary": [summary]}
                    ).to_excel(writer, sheet_name="Summary", index=False)

            output.seek(0)
            return output.getvalue()

        except Exception as exc:
            self._logger.exception("Excel generation failed.")
            raise ServiceError("Failed to generate Excel report.") from exc

    # ----------------------------------------------------------------
    # PowerPoint
    # ----------------------------------------------------------------

    def to_pptx(
        self,
        data: Dict[str, Any],
        summary: str = "",
    ) -> bytes:
        """
        Generate a PowerPoint deck with KPI slides.

        Args:
            data: Analytics snapshot dict.
            summary: AI-written text summary.

        Returns:
            PPTX file as bytes.
        """
        try:
            from pptx import Presentation
            from pptx.util import Inches, Pt
            from pptx.dml.color import RGBColor

            prs = Presentation()
            prs.slide_width = Inches(13.333)
            prs.slide_height = Inches(7.5)

            # Title slide
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            title = slide.shapes.title
            if title:
                title.text = "HR Workforce Report"
            subtitle = slide.placeholders[1] if len(slide.placeholders) > 1 else None
            if subtitle:
                subtitle.text = f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            # KPI slide
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            txBox = slide.shapes.add_textbox(
                Inches(0.5), Inches(0.3), Inches(12), Inches(0.8),
            )
            tf = txBox.text_frame
            tf.text = f"Total Employees: {data.get('total_headcount', 'N/A')}"

            # Summary slide
            if summary:
                slide = prs.slides.add_slide(prs.slide_layouts[6])
                txBox = slide.shapes.add_textbox(
                    Inches(0.5), Inches(0.3), Inches(12), Inches(6),
                )
                tf = txBox.text_frame
                tf.text = "AI Summary"
                p = tf.add_paragraph()
                p.text = summary
                p.font.size = Pt(16)

            buf = io.BytesIO()
            prs.save(buf)
            buf.seek(0)
            return buf.getvalue()

        except Exception as exc:
            self._logger.exception("PPTX generation failed.")
            raise ServiceError(
                "Failed to generate PowerPoint report."
            ) from exc

    # ----------------------------------------------------------------
    # PDF
    # ----------------------------------------------------------------

    def to_pdf(
        self,
        data: Dict[str, Any],
        summary: str = "",
    ) -> bytes:
        """
        Generate a PDF report with KPIs, tables, and summary.

        Args:
            data: Analytics snapshot dict.
            summary: AI-written text summary.

        Returns:
            PDF file as bytes.
        """
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import inch
            from reportlab.pdfgen import canvas
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import (
                Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
            )
            from reportlab.lib import colors

            buf = io.BytesIO()
            doc = SimpleDocTemplate(
                buf, pagesize=A4,
                leftMargin=inch, rightMargin=inch,
                topMargin=inch, bottomMargin=inch,
            )
            styles = getSampleStyleSheet()
            story = []

            # Title
            story.append(Paragraph("HR Workforce Report", styles["Title"]))
            story.append(
                Paragraph(
                    f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    styles["Normal"],
                )
            )
            story.append(Spacer(1, 0.25 * inch))

            # KPIs
            story.append(Paragraph("Key Metrics", styles["Heading2"]))
            kpis = [
                f"Total Employees: {data.get('total_headcount', 'N/A')}",
                f"Average Tenure: {data.get('average_tenure_years', 'N/A')} years",
            ]
            for kpi in kpis:
                story.append(Paragraph(kpi, styles["Normal"]))
            story.append(Spacer(1, 0.2 * inch))

            # Department table
            dept_data = data.get("by_department", [])
            if dept_data:
                story.append(Paragraph("By Department", styles["Heading3"]))
                table_data = [["Department", "Count"]]
                for row in dept_data:
                    table_data.append([str(row.get("department", "")), str(row.get("count", 0))])
                t = Table(table_data)
                t.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A365D")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTSIZE", (0, 0), (-1, -1), 10),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                    ])
                )
                story.append(t)
                story.append(Spacer(1, 0.2 * inch))

            # AI summary
            if summary:
                story.append(Paragraph("AI Summary", styles["Heading2"]))
                story.append(Paragraph(summary, styles["Normal"]))

            doc.build(story)
            buf.seek(0)
            return buf.getvalue()

        except Exception as exc:
            self._logger.exception("PDF generation failed.")
            raise ServiceError(
                "Failed to generate PDF report."
            ) from exc
