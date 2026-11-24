import {authenticatedRequest} from "./api.js";
export const firmwareList = options => authenticatedRequest("/ota/firmware",options);
export const otaDevices = options => authenticatedRequest("/ota/devices",options);
export const otaDeployments = options => authenticatedRequest("/ota/deployments",options);
export function uploadFirmware(file,manifest,notes) {
  const body = new FormData();
  body.append("file",file);body.append("manifest",manifest);body.append("notes",notes);
  return authenticatedRequest("/ota/firmware",{method:"POST",body});
}
export const firmwareAction = (id,action) => {
  if(!Number.isSafeInteger(id) || !["verify","release","withdraw"].includes(action))throw new Error("Thao tác firmware không hợp lệ.");
  return authenticatedRequest(`/ota/firmware/${id}/${action}`,{method:"POST"});
};
export const previewOta = body => authenticatedRequest("/ota/deployments/preview",{method:"POST",body});
export const createOta = body => authenticatedRequest("/ota/deployments",{method:"POST",body:{...body,confirmed:true}});
export const cancelOta = id => authenticatedRequest(`/ota/jobs/${id}/cancel`,{method:"POST"});

export const otaState = state => ({DRAFT:"Bản nháp",VERIFIED:"Đã xác minh",RELEASED:"Đã phát hành",WITHDRAWN:"Đã thu hồi",
  QUEUED:"Chờ gửi",PUBLISHING:"Đang gửi",SENT:"Đã gửi yêu cầu",ACCEPTED:"Thiết bị đã nhận",DOWNLOADING:"Đang tải",
  VERIFYING:"Đang xác minh",REBOOTING:"Đang khởi động lại",CONFIRMED:"Đã xác nhận bản mới",REJECTED:"Bị từ chối",
  FAILED:"Thất bại",CANCELLED:"Đã hủy trước khi gửi",ROLLED_BACK:"Đã quay về bản trước",RESULT_UNKNOWN:"Chưa xác định kết quả"}[state] || state);
