import { useEffect, useRef } from "react";
import "../styles/feedback-dialog.css";

export default function DecommissionDialog({target, onCancel, onConfirm}) {
  const cancelButton = useRef(null);
  const cancelRef = useRef(onCancel);
  cancelRef.current = onCancel;
  useEffect(() => {
    if (!target) return;
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    cancelButton.current?.focus();
    const keydown = event => {
      if (event.key === "Escape") { event.preventDefault(); cancelRef.current(); }
      if (event.key === "Tab") {
        const buttons = cancelButton.current.closest("section").querySelectorAll("button");
        const first = buttons[0], last = buttons[buttons.length-1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown",keydown);
    return () => {
      document.removeEventListener("keydown",keydown);
      document.body.style.overflow = overflow;
      previous?.focus?.();
    };
  }, [target]);
  if (!target) return null;
  return <div className="feedback-overlay"><section className="feedback-dialog feedback-dialog--error decommission-dialog"
    role="alertdialog" aria-modal="true" aria-labelledby="decommission-title" aria-describedby="decommission-message">
    <h2 id="decommission-title">Xác nhận ngừng sử dụng</h2>
    <p id="decommission-message">Ngừng sử dụng <strong>{target.name || target.code}</strong> (<strong>{target.code}</strong>)?
      Kết nối thiết bị sẽ bị thu hồi. Lịch sử vẫn được giữ. Sau thao tác này không thể khôi phục đăng ký trên hệ thống.</p>
    <div className="form-actions"><button ref={cancelButton} className="outline-button" type="button" onClick={onCancel}>Hủy</button>
      <button className="primary-button" type="button" onClick={onConfirm}>Xác nhận ngừng sử dụng</button></div>
  </section></div>;
}
