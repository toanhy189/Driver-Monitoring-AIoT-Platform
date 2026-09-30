import "../styles/login.css";

function Login({ onLogin }) {
  const handleSubmit = (event) => {
    event.preventDefault();
    onLogin();
  };

  return (
    <main className="login-page">
      <div className="login-card">
        <h1 className="login-title">
          GIÁM SÁT TÀI XẾ AIoT
        </h1>

        <p className="login-subtitle">
          Driver Monitoring System
        </p>

        <form
          className="login-form"
          onSubmit={handleSubmit}
        >
          <label htmlFor="username">
            Tên đăng nhập
          </label>

          <input
            id="username"
            type="text"
            placeholder="Enter username"
          />

          <label htmlFor="password">
            Mật khẩu
          </label>

          <input
            id="password"
            type="password"
            placeholder="Enter password"
          />

          <button
            className="login-button"
            type="submit"
          >
            Đăng nhập
          </button>
        </form>
      </div>
    </main>
  );
}

export default Login;