from odoo import http
from odoo.http import request


class GoldVerseLaundryReceiptPrintController(http.Controller):
    @http.route("/goldverse/laundry_order/<int:order_id>/print_receipt", type="http", auth="user", website=False)
    def goldverse_print_laundry_receipt(self, order_id, **kwargs):
        order = request.env["aimaze.laundry.order"].browse(order_id)
        if not order.exists():
            return request.not_found()
        order.check_access("read")

        report_action = request.env.ref("aimaze_laundry_management.action_report_laundry_order_receipt")
        report_html, _ = report_action._render_qweb_html(report_action.report_name, order.ids)
        if isinstance(report_html, bytes):
            report_html = report_html.decode("utf-8")

        print_script = """
<script type="text/javascript">
    (function () {
        var printTriggered = false;

        function triggerPrint() {
            if (printTriggered) {
                return;
            }
            printTriggered = true;
            setTimeout(function () {
                window.focus();
                window.print();
            }, 250);
        }

        if (document.readyState === "complete") {
            triggerPrint();
        } else {
            window.addEventListener("load", triggerPrint);
        }

        window.addEventListener("afterprint", function () {
            setTimeout(function () {
                window.close();
            }, 150);
        });
    })();
</script>
</body>"""

        html = report_html.replace("</body>", print_script, 1) if "</body>" in report_html else report_html + print_script
        return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])
