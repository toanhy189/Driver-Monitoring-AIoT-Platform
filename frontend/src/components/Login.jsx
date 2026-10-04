  import { useState } from "react";
  import "../styles/login.css";

  const BACKEND_HOST = import.meta.env.VITE_BACKEND_HOST;
  const API_STR = import.meta.env.VITE_API_STR;

  function Login({ onLogin }) {
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");

    const handleSubmit = async (event) => {
      event.preventDefault();

      const response = await fetch(`${BACKEND_HOST}${API_STR}/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: username,
          password: password,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        alert(data.detail);
        return;
      }

      localStorage.setItem("access_token", data.access_token);

      onLogin();
    };

    return (
      <main className="login-page">
        <div className="login-card">

          <h1 className="login-title">GIÁM SÁT TÀI XẾ AIoT</h1>
          <p className="login-subtitle">Driver Monitoring System</p>

          <form className="login-form" onSubmit={handleSubmit}>
            <label htmlFor="username">
              Tên đăng nhập
            </label>

            <input
              id="username" type="text"
              placeholder="Enter username" value={username}
              onChange={(event) => setUsername(event.target.value)}
            />

            <label htmlFor="password">
              Mật khẩu
            </label>

            <input
              id="password" type="password"
              placeholder="Enter password" value={password}
              onChange={(event) => setPassword(event.target.value)}
            />

            <button className="login-button" type="submit">
              Đăng nhập
            </button>
          </form>
        </div>
      </main>
    );
  }

  export default Login;