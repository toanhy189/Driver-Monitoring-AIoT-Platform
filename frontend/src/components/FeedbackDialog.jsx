import { useEffect, useRef } from "react";
import "../styles/feedback-dialog.css";

function FeedbackDialog({ feedback, onClose }) {
  const closeButton = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!feedback) return;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButton.current?.focus();
    const onKeyDown = event => {
      if (event.key === "Escape") onCloseRef.current();
      if (event.key === "Tab") {
        event.preventDefault();
        closeButton.current?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus?.();
    };
  }, [feedback]);

  if (!feedback || typeof document === "undefined") return null;

  const isError = feedback.tone === "error";
  return (
    <div className="feedback-overlay">
      <section className={`feedback-dialog feedback-dialog--${isError ? "error" : "success"}`}
        role="alertdialog" aria-modal="true" aria-labelledby="feedback-title" aria-describedby="feedback-message">
        <span className="feedback-dialog-icon" aria-hidden="true">{isError ? "!" : "✓"}</span>
        <h2 id="feedback-title">{feedback.title}</h2>
        <p id="feedback-message">{feedback.message}</p>
        <button ref={closeButton} type="button" className="primary-button" onClick={onCloseRef.current}>Xác nhận</button>
      </section>
    </div>
  );
}

export default FeedbackDialog;
