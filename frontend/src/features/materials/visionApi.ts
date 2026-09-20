import { request } from '../../shared/api'
import type { MaterialBatch, VisionAdoption } from './types'
export interface RecognitionBlock {kind:'text'|'formula'|'table'|'diagram';title:string;content:string;uncertain:boolean;note:string}
export interface RecognitionJob {
  id:string;page:number;process_id:string;status:'queued'|'running'|'ready'|'failed'|'interrupted'
  provider_name:string;model:string;result:{blocks:RecognitionBlock[];issues:string[]}|null
  error:string|null;review:'pending'|'accepted'|'rejected';review_note:string;revision:number;plan_hash:string
}
export interface RecognitionPlan {plan_hash:string;page:number;provider_name:string;model:string;base_url:string;image_bytes:number;text_characters:number;maximum_calls:number;existing_job_id:string|null}
export interface RecognitionPage {filename:string;page:number;preview:string;text:string;jobs:RecognitionJob[];file_revision:number;editable:boolean;adoption:VisionAdoption|null}
export interface PageScope {batchId:string;fileId:string;processId:string;page:number}
const fileBase=(s:PageScope)=>`/material-batches/${s.batchId}/files/${s.fileId}`
const pageBase=(s:PageScope)=>`${fileBase(s)}/processes/${s.processId}/pages/${s.page}`
export const visionApi={
  adopt:(s:PageScope,j:RecognitionJob,fileRevision:number,selected:boolean)=>request<MaterialBatch>(`${fileBase(s)}/vision-jobs/${j.id}/adoption`,{method:'POST',body:JSON.stringify({expected_file_revision:fileRevision,expected_recognition_revision:j.revision,selected})}),
  view:(s:PageScope)=>request<RecognitionPage>(`${pageBase(s)}/vision`),
  plan:(s:PageScope)=>request<RecognitionPlan>(`${pageBase(s)}/vision-plan`),
  start:(s:PageScope,id:string,hash:string)=>request<RecognitionJob>(`${pageBase(s)}/vision`,{method:'POST',body:JSON.stringify({request_id:id,plan_hash:hash})}),
  job:(s:PageScope,id:string)=>request<RecognitionJob>(`${fileBase(s)}/vision-jobs/${id}`),
  review:(s:PageScope,j:RecognitionJob,decision:'accepted'|'rejected',note:string)=>request<RecognitionJob>(`${fileBase(s)}/vision-jobs/${j.id}/review`,{
    method:'PATCH',body:JSON.stringify({expected_revision:j.revision,decision,note}),
  }),
}
