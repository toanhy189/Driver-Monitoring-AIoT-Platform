import { useEffect, useRef, useState } from "react";
import { authenticatedRequest } from "../services/api.js";
import { roleLabel } from "../services/permissions.js";

export default function AccountPanel({ user, onClose, onLogout }) {
  const [profile, setProfile] = useState({ fullname: user?.fullname || "", email: user?.email || "", phone: user?.phone || "" });
  const [passwords, setPasswords] = useState({ current_password: "", new_password: "" });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const dialog = useRef(null);
  const close = useRef(onClose);
  useEffect(() => { close.current = onClose; }, [onClose]);
  useEffect(() => {
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    const node = dialog.current;
    const controls = () => [...node.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]')]
      .filter(element => element.getClientRects().length);
    document.body.style.overflow = "hidden";
    const frame = requestAnimationFrame(() => controls()[0]?.focus());
    function handleKey(event) {
      if (event.key === "Escape") { event.preventDefault(); close.current(); return; }
      if (event.key !== "Tab") return;
      const items = controls(), first = items[0], last = items.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    node.addEventListener("keydown", handleKey);
    return () => {
      cancelAnimationFrame(frame);
      node.removeEventListener("keydown", handleKey);
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);
  async function submit(event, password = false) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      await authenticatedRequest(password ? "/me/password" : "/me", {
        method: password ? "POST" : "PUT", body: password ? passwords : profile,
      });
      if (password) { onLogout(); return; }
      window.dispatchEvent(new Event("driver:profile-updated"));
      setNotice("Đã lưu thông tin tài khoản.");
    } catch (cause) {
      if (cause.status === 401) onLogout(); else setError(cause.message);
    } finally { setBusy(false); }
  }
  return <div className="video-modal-backdrop"><section ref={dialog} className="surface-card account-modal" role="dialog" aria-modal="true" aria-labelledby="account-title">
    <div className="section-heading"><div><h2 id="account-title">Tài khoản của tôi</h2><span className="account-badge">{user?.username} · {roleLabel(user?.role)}</span></div><button className="outline-button" onClick={onClose}>Đóng</button></div>
    <form className="form-grid-2" onSubmit={event => submit(event)}>
      {[["fullname", "Họ tên", "text"], ["email", "Email", "email"], ["phone", "Điện thoại", "tel"]].map(([key, label, type]) => <label key={key} className={`form-field${key === "fullname" ? " form-field--wide" : ""}`}>{label}<input required type={type} value={profile[key]} onChange={event => setProfile({ ...profile, [key]: event.target.value })} /></label>)}
      <div className="inline-actions inline-actions--end form-field--wide"><button className="primary-button" disabled={busy}>Lưu thông tin</button></div>
    </form>
    <section className="account-password"><h3>Đổi mật khẩu</h3><p className="muted-note">Đổi mật khẩu sẽ kết thúc các phiên đăng nhập hiện tại.</p>
      <form className="form-grid-2" onSubmit={event => submit(event, true)}>
        <label className="form-field">Mật khẩu hiện tại<input required type="password" autoComplete="current-password" value={passwords.current_password} onChange={event => setPasswords({ ...passwords, current_password: event.target.value })} /></label>
        <label className="form-field">Mật khẩu mới (ít nhất 8 ký tự)<input required minLength={8} maxLength={128} type="password" autoComplete="new-password" value={passwords.new_password} onChange={event => setPasswords({ ...passwords, new_password: event.target.value })} /></label>
        <div className="inline-actions inline-actions--end form-field--wide"><button className="primary-button" disabled={busy}>Đổi mật khẩu</button></div>
      </form>
    </section>
    {error && <p role="alert" className="notice-error">{error}</p>}{notice && <p role="status" className="notice-success">{notice}</p>}
  </section></div>;
}
