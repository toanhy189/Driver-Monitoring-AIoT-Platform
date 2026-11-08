import { useState } from "react";
import { authenticatedRequest } from "../services/api.js";

export default function AccountPanel({ user, onClose, onLogout }) {
  const [profile, setProfile] = useState({ fullname: user?.fullname || "", email: user?.email || "", phone: user?.phone || "" });
  const [passwords, setPasswords] = useState({ current_password: "", new_password: "" });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  async function submit(event, password = false) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      await authenticatedRequest(password ? "/me/password" : "/me", {
        method: password ? "POST" : "PUT", body: password ? passwords : profile,
      });
      if (password) { onLogout(); return; }
      setNotice("Đã lưu thông tin tài khoản.");
    } catch (cause) {
      if (cause.status === 401) onLogout(); else setError(cause.message);
    } finally { setBusy(false); }
  }
  return <div className="video-modal-backdrop"><section className="surface-card" role="dialog" aria-modal="true" aria-labelledby="account-title" style={{ maxWidth: 560, width: "95%", maxHeight: "90vh", overflow: "auto", padding: 24 }}>
    <div className="section-heading"><h2 id="account-title">Tài khoản của tôi</h2><button className="outline-button" onClick={onClose}>Đóng</button></div>
    <p>{user?.username} · {user?.role}</p>
    <form onSubmit={event => submit(event)}>
      {[["fullname", "Họ tên", "text"], ["email", "Email", "email"], ["phone", "Điện thoại", "tel"]].map(([key, label, type]) => <label key={key} style={{ display: "block", marginBottom: 12 }}>{label}<input required type={type} value={profile[key]} onChange={event => setProfile({ ...profile, [key]: event.target.value })} /></label>)}
      <button className="primary-button" disabled={busy}>Lưu thông tin</button>
    </form>
    <h3>Đổi mật khẩu</h3><p>Đổi mật khẩu sẽ kết thúc các phiên đăng nhập hiện tại.</p>
    <form onSubmit={event => submit(event, true)}>
      <label style={{ display: "block" }}>Mật khẩu hiện tại<input required type="password" autoComplete="current-password" value={passwords.current_password} onChange={event => setPasswords({ ...passwords, current_password: event.target.value })} /></label>
      <label style={{ display: "block", marginBottom: 12 }}>Mật khẩu mới (ít nhất 8 ký tự)<input required minLength={8} maxLength={128} type="password" autoComplete="new-password" value={passwords.new_password} onChange={event => setPasswords({ ...passwords, new_password: event.target.value })} /></label>
      <button className="primary-button" disabled={busy}>Đổi mật khẩu</button>
    </form>
    {error && <p role="alert" className="notice-error">{error}</p>}{notice && <p role="status" className="notice-success">{notice}</p>}
  </section></div>;
}
