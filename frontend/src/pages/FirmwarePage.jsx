import {useCallback,useEffect,useState} from "react";
import AppShell from "../components/AppShell.jsx";
import {hasPermission} from "../services/permissions.js";
import {firmwareList,otaDevices,otaDeployments,uploadFirmware,firmwareAction,previewOta,createOta,cancelOta,otaState} from "../services/ota.js";
import "../styles/firmware.css";

export default function FirmwarePage({user,realtime,onDashboard,onDevices,onCommands,onAlerts,onOpenDevice,onLogout,onUnauthorized}) {
  const allowed=hasPermission(user?.role,"firmware:manage");
  const [tab,setTab]=useState("firmware"),[catalog,setCatalog]=useState(null),[devices,setDevices]=useState([]),[deployments,setDeployments]=useState([]);
  const [error,setError]=useState(""),[notice,setNotice]=useState(""),[busy,setBusy]=useState(false);
  const [file,setFile]=useState(null),[manifestFile,setManifestFile]=useState(null),[notes,setNotes]=useState("");
  const [artifactId,setArtifactId]=useState(""),[selected,setSelected]=useState([]),[preview,setPreview]=useState(null);
  const reload=useCallback(async signal=>{
    if(!allowed)return;
    try {
      const [firmware,nodes,batches]=await Promise.all([firmwareList({signal}),otaDevices({signal}),otaDeployments({signal})]);
      if(signal?.aborted)return;
      setCatalog(firmware);setDevices(nodes);setDeployments(batches);
    } catch(err) {if(err.name!=="AbortError"){setError(err.message);if(err.status===401)onUnauthorized();}}
  },[allowed,onUnauthorized]);
  useEffect(()=>{const controller=new AbortController();reload(controller.signal);
    const timer=setInterval(()=>reload(controller.signal),5000);return()=>{controller.abort();clearInterval(timer);};},[reload]);
  const execute=async operation=>{
    if(busy)return;setBusy(true);setError("");setNotice("");
    try {await operation();await reload();}
    catch(err){setError(err.message);if(err.status===401)onUnauthorized();}
    finally{setBusy(false);}
  };
  const chooseForJob=(job,artifact)=>{
    setArtifactId(String(artifact));setSelected([job.device_id]);setPreview(null);setTab("deploy");
  };
  const body={artifact_id:Number(artifactId),device_ids:selected};
  return <AppShell user={user} activePage="firmware" serverConnected={realtime?.connected} onDashboard={onDashboard}
    onDevices={onDevices} onCommands={onCommands} onAlerts={onAlerts} onLogout={onLogout}>
    <div className="page-title"><h1>Firmware và cập nhật OTA</h1><p>Quản lý phiên bản ESP32, cập nhật và theo dõi kết quả trên thiết bị</p></div>
    {!allowed ? <p role="alert">Chỉ quản trị viên được quản lý firmware.</p> : <>
      <nav className="ota-tabs" aria-label="Quản lý OTA">{[["firmware","Kho firmware"],["deploy","Cập nhật thiết bị"],["history","Theo dõi cập nhật"]].map(([key,label])=>
        <button key={key} type="button" className={tab===key?"primary-button":"outline-button"} aria-pressed={tab===key} onClick={()=>setTab(key)}>{label}</button>)}
      </nav>
      {error && <p className="notice-error" role="alert">{error}</p>}{notice && <p className="notice-success" role="status">{notice}</p>}
      {!catalog && !error && <p role="status">Đang tải dữ liệu OTA…</p>}
      {catalog && (!catalog.configuration.enabled || !catalog.configuration.public_key_ready || !catalog.configuration.download_origin_ready) &&
        <p className="warning-banner" role="status">Chưa sẵn sàng gửi OTA. Cần bật dịch vụ, cấu hình khóa xác minh và địa chỉ tải firmware. Vẫn có thể chuẩn bị kho firmware.</p>}
      {tab==="firmware" && <>
        <section className="surface-card ota-panel"><h2>Upload firmware</h2><p>Chọn application firmware.bin và manifest JSON đã ký trên máy build. Khóa ký bí mật được giữ ngoài hệ thống web.</p>
          <form className="ota-upload" onSubmit={event=>{event.preventDefault();execute(async()=>{
            if(!file||!manifestFile)throw new Error("Chọn cả firmware .bin và manifest .json.");
            if(file.size>2097152 || manifestFile.size>8192)throw new Error("Firmware tối đa 2 MiB; manifest tối đa 8 KiB.");
            await uploadFirmware(file,await manifestFile.text(),notes);setNotice("Đã upload bản nháp. Tiếp theo xác minh chữ ký rồi phát hành.");
          });}}>
            <label>File firmware (.bin)<input type="file" accept=".bin" required disabled={busy} onChange={event=>setFile(event.target.files[0]||null)} /></label>
            <label>Manifest đã ký (.json)<input type="file" accept=".json" required disabled={busy} onChange={event=>setManifestFile(event.target.files[0]||null)} /></label>
            <label>Ghi chú<textarea value={notes} maxLength={2000} onChange={event=>setNotes(event.target.value)} /></label>
            <button className="primary-button" disabled={busy} type="submit">{busy?"Đang xử lý…":"Upload bản nháp"}</button>
          </form></section>
        <section className="surface-card ota-panel"><h2>Kho firmware</h2>{catalog?.items.length===0 && <p>Chưa có firmware.</p>}
          <div className="ota-table-wrap"><table className="ota-table"><thead><tr><th>Phiên bản</th><th>Phần cứng</th><th>Toàn vẹn</th><th>Trạng thái</th><th>Thao tác</th></tr></thead>
            <tbody>{catalog?.items.map(item=><tr key={item.id}><td><strong>{item.version}</strong><small>{item.notes}</small></td><td>{item.hardware_version}</td>
              <td>{(item.size_bytes/1024).toFixed(1)} KiB<details><summary>SHA-256</summary><code>{item.sha256}</code></details></td>
              <td>{otaState(item.state)}{item.verification_error && <p className="text-red">{item.verification_error}</p>}</td><td><div className="ota-actions">
                {["DRAFT","VERIFIED"].includes(item.state) && <button className="outline-button" disabled={busy} onClick={()=>execute(()=>firmwareAction(item.id,"verify"))}>Xác minh chữ ký</button>}
                {item.state==="VERIFIED" && <button className="primary-button" disabled={busy} onClick={()=>execute(()=>firmwareAction(item.id,"release"))}>Phát hành</button>}
                {item.state==="RELEASED" && <button className="outline-button" disabled={busy} onClick={()=>{setArtifactId(String(item.id));setPreview(null);setTab("deploy");}}>Chọn cập nhật</button>}
                {item.state!=="WITHDRAWN" && <button className="outline-button" disabled={busy} onClick={()=>{if(window.confirm(`Thu hồi firmware ${item.version}? Đợt chưa gửi sẽ bị chặn; phần đã tải có thể tiếp tục.`))execute(()=>firmwareAction(item.id,"withdraw"));}}>Thu hồi</button>}
              </div></td></tr>)}</tbody></table></div></section>
      </>}
      {tab==="deploy" && <section className="surface-card ota-panel"><h2>Cập nhật thiết bị</h2><p>Chọn firmware đã phát hành và thiết bị. Nên thử một ESP32 trước khi cập nhật nhiều thiết bị.</p>
        <label className="ota-artifact-select">Firmware mục tiêu<select value={artifactId} onChange={event=>{setArtifactId(event.target.value);setPreview(null);}}>
          <option value="">Chọn firmware đã phát hành</option>{catalog?.items.filter(item=>item.state==="RELEASED").map(item=><option key={item.id} value={item.id}>{item.version} — {item.hardware_version}</option>)}</select></label>
        <div className="ota-table-wrap"><table className="ota-table"><thead><tr><th>Chọn</th><th>Thiết bị</th><th>Phiên bản hiện tại</th><th>Phần cứng</th><th>Kết nối / OTA</th></tr></thead>
          <tbody>{devices.map(device=><tr key={device.id}><td><input type="checkbox" aria-label={`Chọn ${device.device_code}`} checked={selected.includes(device.id)} onChange={event=>{
            setSelected(current=>event.target.checked?[...current,device.id]:current.filter(id=>id!==device.id));setPreview(null);}} /></td>
            <td>{device.device_code}<small>{device.name}</small></td><td>{device.firmware_version||"Chưa có"}</td><td>{device.hardware_version||"Chưa có"}</td>
            <td>{device.status} · {device.lifecycle_state}<small>{device.ota_capabilities?.supported?`OTA sẵn sàng; phân vùng ${Math.floor(device.ota_capabilities.max_image_bytes/1024)} KiB`:"Chưa có firmware OTA nền"}</small></td></tr>)}</tbody></table></div>
        <button className="outline-button" disabled={busy||!artifactId||selected.length===0} onClick={()=>execute(async()=>setPreview(await previewOta(body)))}>Kiểm tra điều kiện</button>
        {preview && <div className="ota-preview"><h3>Kết quả kiểm tra</h3><ul>{preview.devices.map(device=><li key={device.id}>{device.device_code}: {device.current_version||"Chưa có"} → {device.target_version} — {device.reason||"Đủ điều kiện"}</li>)}</ul>
          <p>{preview.notice}</p><button className="primary-button" disabled={busy||!preview.ready} onClick={()=>{
            if(window.confirm("Xác nhận cập nhật firmware cho các thiết bị đã chọn? Thiết bị sẽ vào bảo trì và tắt cảnh báo tự động. Sau cập nhật cần kiểm tra rồi kích hoạt lại."))execute(async()=>{
              const result=await createOta(body);setPreview(null);setSelected([]);setNotice(`Đã tạo đợt cập nhật #${result.id}.`);setTab("history");
            });}}>Xác nhận cập nhật</button></div>}
      </section>}
      {tab==="history" && <section className="surface-card ota-panel"><h2>Theo dõi cập nhật</h2><p>100% tải chưa có nghĩa là cài đặt thành công. Kết quả cần xác nhận sau khởi động với đúng phiên bản và hash.</p>
        {deployments.length===0 && <p>Chưa có đợt cập nhật.</p>}{deployments.map(deployment=><article className="ota-batch" key={deployment.id}><h3>Đợt #{deployment.id}</h3>
          {deployment.jobs.map(job=><div className="ota-job" key={job.id}><div className="ota-job-heading"><strong>{job.device_code}: {job.previous_version||"Chưa có"} → {job.target_version}</strong><span>{otaState(job.state)}</span></div>
            <p>Tải: {job.bytes_received.toLocaleString()} / {job.size_bytes.toLocaleString()} byte ({job.progress_percent}%)</p><progress value={job.bytes_received} max={job.size_bytes} aria-label={`Tiến độ tải ${job.device_code}`} />
            {job.error && <p className="notice-error">{job.error}</p>}{job.installed_version && <p>Thiết bị báo phiên bản: {job.installed_version}</p>}
            <div className="ota-actions">{job.state==="QUEUED" && <button className="outline-button" disabled={busy} onClick={()=>execute(()=>cancelOta(job.id))}>Hủy phần chưa gửi</button>}
              {["FAILED","REJECTED","ROLLED_BACK"].includes(job.state) && <button className="outline-button" disabled={busy} onClick={()=>chooseForJob(job,deployment.artifact_id)}>Chuẩn bị thử lại</button>}
              {job.state==="CONFIRMED" && job.previous_artifact_id && <button className="outline-button" disabled={busy} onClick={()=>chooseForJob(job,job.previous_artifact_id)}>Chuẩn bị về bản trước</button>}
              <button className="outline-button" onClick={()=>onOpenDevice({id:job.device_id})}>Mở thiết bị / kết thúc bảo trì</button></div>
            <details><summary>Diễn biến cập nhật</summary>{job.installed_sha256 && <p>Hash ảnh đang chạy: <code>{job.installed_sha256}</code></p>}<ol>{job.events.map(event=><li key={event.id}><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString("vi-VN")}</time>: {otaState(event.state)}{event.detail?` — ${event.detail}`:""}</li>)}</ol></details>
          </div>)}</article>)}
      </section>}
    </>}
  </AppShell>;
}
