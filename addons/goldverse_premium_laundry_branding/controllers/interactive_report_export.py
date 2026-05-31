import json

from odoo import http
from odoo.http import content_disposition, request


class GoldverseInteractiveReportExportController(http.Controller):
    @http.route(
        "/goldverse/interactive_report/xlsx",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def goldverse_interactive_report_xlsx(self, report_key=None, options=None, **_kw):
        parsed_options = json.loads(options or "{}")
        content, filename = request.env["account.interactive.report"].goldverse_xlsx_content(
            report_key or "profit_and_loss",
            parsed_options,
        )
        headers = [
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", content_disposition(filename)),
        ]
        return request.make_response(content, headers=headers)
