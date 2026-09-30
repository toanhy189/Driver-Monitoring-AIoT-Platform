// là điểm điều hướng đến các trang khác
// các tuần sau có thể đưa các điều kiện ktra vào funtion App(), sau đó return đến trang nào đó
import { useState } from "react";

import Login from "./components/Login.jsx";
import Dashboard from "./components/Dashboard.jsx";

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  if (!isLoggedIn) {
    return (
      <Login
        onLogin={() => setIsLoggedIn(true)}
      />
    );
  }

  return (
    <Dashboard
      onLogout={() => setIsLoggedIn(false)}
    />
  );
}

export default App;