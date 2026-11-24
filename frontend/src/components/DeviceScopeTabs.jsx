export default function DeviceScopeTabs({ devices, value, onChange }) {
  const archived = devices.filter(device => device.lifecycle_state === "DECOMMISSIONED").length;
  return <div className="device-scope-tabs" role="group" aria-label="Phạm vi thiết bị">
    <button type="button" className={value === "current" ? "primary-button" : "outline-button"} aria-pressed={value === "current"} onClick={() => onChange("current")}>Thiết bị hiện tại ({devices.length - archived})</button>
    <button type="button" className={value === "archived" ? "primary-button" : "outline-button"} aria-pressed={value === "archived"} onClick={() => onChange("archived")}>Đã ngừng sử dụng ({archived})</button>
  </div>;
}
