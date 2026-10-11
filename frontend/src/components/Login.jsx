import { useState } from "react";
import { apiRequest } from "../services/api.js";
import { getCurrentUser } from "../services/auth.js";
import "../styles/login.css";

function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setErrorMessage("");
    setIsSubmitting(true);
    let step = "login";

    try {
      const data = await apiRequest("/login", {
        method: "POST",
        body: { username, password },
      });
      if (typeof data?.access_token !== "string" || !data.access_token) {
        throw new Error("Máy chủ không trả token đăng nhập hợp lệ.");
      }
      step = "profile";
      const user = await getCurrentUser({ token: data.access_token });
      onLogin({ token: data.access_token, user });
    } catch (error) {
      setErrorMessage(error.status === 401 ?
        (step === "login" ? "Sai tên đăng nhập hoặc mật khẩu." : "Phiên đăng nhập không hợp lệ. Vui lòng thử lại.") :
        error.status === 403 ? "Bạn không có quyền truy cập." :
        error.message || "Không thể đăng nhập. Vui lòng thử lại.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="login-page">
      <div className="login-card">
        <h1 className="login-title">GIÁM SÁT TÀI XẾ AIoT</h1>
        <p className="login-subtitle">Driver Monitoring System</p>

        <form className="login-form" onSubmit={handleSubmit}>
          <label htmlFor="username">Tên đăng nhập</label>
          <input
            id="username" type="text" autoComplete="username" required
            placeholder="Enter username" value={username}
            onChange={(event) => setUsername(event.target.value)}
          />

          <label htmlFor="password">Mật khẩu</label>
          <input
            id="password" type="password" autoComplete="current-password" required
            placeholder="Enter password" value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          {errorMessage && <p className="login-error" role="alert">{errorMessage}</p>}
          <button className="login-button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Đang đăng nhập…" : "Đăng nhập"}
          </button>
        </form>
      </div>
    </main>
  );
}

export default Login;
