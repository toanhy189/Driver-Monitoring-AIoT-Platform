import { useState } from "react";
import { apiRequest } from "../services/api.js";
import { getCurrentUser } from "../services/auth.js";
import "../styles/login.css";

function SignUp({ onSignUp, onOpenLogin }) {
  const [fields, setFields] = useState({
    fullname: "",
    username: "",
    email: "",
    phone: "",
    password: "",
    confirmPassword: "",
  });
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [step, setStep] = useState(1);

  const updateField = event => {
    const { name, value } = event.target;
    setFields(current => ({ ...current, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setErrorMessage("");

    if (step === 1) {
      setStep(2);
      return;
    }

    setIsSubmitting(true);
    let requestStep = "register";

    try {
      await apiRequest("/register", {
        method: "POST",
        body: {
          fullname: fields.fullname,
          username: fields.username,
          email: fields.email,
          phone: fields.phone,
          password: fields.password,
          confirm_password: fields.confirmPassword,
        },
      });

      requestStep = "login";
      const data = await apiRequest("/login", {
        method: "POST",
        body: { username: fields.username, password: fields.password },
      });
      if (typeof data?.access_token !== "string" || !data.access_token) {
        throw new Error("Máy chủ không trả token đăng nhập hợp lệ.");
      }

      requestStep = "profile";
      const user = await getCurrentUser({ token: data.access_token });
      onSignUp({ token: data.access_token, user });
    } catch (error) {
      if (requestStep === "register") {
        setErrorMessage(error.message || "Không thể tạo tài khoản. Vui lòng thử lại.");
      } else {
        onOpenLogin?.(
          "Tài khoản đã được tạo nhưng đăng nhập tự động thất bại. Vui lòng đăng nhập bằng tài khoản vừa đăng ký."
        );
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="login-page">
      <div className="login-card signup-card">
        <h1 className="login-title">GIÁM SÁT TÀI XẾ AIoT</h1>
        <p className="login-subtitle">Driver Monitoring System</p>

        <div className="signup-layout">
          <aside className="signup-steps" aria-label="Các bước đăng ký">
            <div className={`signup-step${step === 1 ? " is-active" : " is-complete"}`}>
              <span>1</span>
              <div><strong>Thông tin cá nhân</strong><small>Thông tin liên hệ của bạn</small></div>
            </div>
            <div className={`signup-step${step === 2 ? " is-active" : ""}`}>
              <span>2</span>
              <div><strong>Thông tin đăng nhập</strong><small>Tạo thông tin tài khoản</small></div>
            </div>
          </aside>

          <form className="login-form signup-form" onSubmit={handleSubmit}>
            {step === 1 ? (
              <>
                <label htmlFor="fullname">Họ và tên</label>
                <input
                  id="fullname" name="fullname" type="text" autoComplete="name" required
                  placeholder="Nhập họ và tên" value={fields.fullname} onChange={updateField}
                />

                <label htmlFor="email">Email</label>
                <input
                  id="email" name="email" type="email" autoComplete="email" required
                  placeholder="Nhập email" value={fields.email} onChange={updateField}
                />

                <label htmlFor="phone">Số điện thoại</label>
                <input
                  id="phone" name="phone" type="tel" autoComplete="tel" required
                  placeholder="Nhập số điện thoại" value={fields.phone} onChange={updateField}
                />
              </>
            ) : (
              <>
                <label htmlFor="username">Tên đăng nhập</label>
                <input
                  id="username" name="username" type="text" autoComplete="username" required
                  placeholder="Nhập tên đăng nhập" value={fields.username} onChange={updateField}
                />

                <label htmlFor="password">Mật khẩu</label>
                <input
                  id="password" name="password" type="password" autoComplete="new-password" required
                  placeholder="Nhập mật khẩu" value={fields.password} onChange={updateField}
                />

                <label htmlFor="confirmPassword">Xác nhận mật khẩu</label>
                <input
                  id="confirmPassword" name="confirmPassword" type="password" autoComplete="new-password" required
                  placeholder="Xác nhận mật khẩu" value={fields.confirmPassword} onChange={updateField}
                />
              </>
            )}

            {errorMessage && <p className="login-error" role="alert">{errorMessage}</p>}
            <div className="signup-form-actions">
              {step === 2 && (
                <button className="login-secondary-button" type="button" disabled={isSubmitting} onClick={() => setStep(1)}>
                  Quay lại
                </button>
              )}
              <button className="login-button" type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Đang tạo tài khoản…" : step === 1 ? "Tiếp tục" : "Đăng ký"}
              </button>
            </div>
          </form>
        </div>
        {onOpenLogin && (
          <button className="login-secondary-button" type="button" onClick={() => onOpenLogin("")}>
            Đã có tài khoản? Đăng nhập
          </button>
        )}
      </div>
    </main>
  );
}

export default SignUp;
