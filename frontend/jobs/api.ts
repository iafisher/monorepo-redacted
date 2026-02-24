import * as kgrpc from "../common/kgrpc";
import * as rpc from "./rpc";

export async function fetchJobs(): Promise<rpc.JobListResponse> {
  return await kgrpc.get("/api/jobs");
}

export async function fetchJobDetail(
  jobName: string,
): Promise<rpc.JobDetailResponse> {
  return await kgrpc.get(`/api/job/${encodeURIComponent(jobName)}`);
}

export async function fetchLog(
  jobName: string,
  timestamp: string,
): Promise<rpc.LogDetailResponse> {
  return await kgrpc.get(
    `/api/log/${encodeURIComponent(jobName)}/${encodeURIComponent(timestamp)}`,
  );
}
