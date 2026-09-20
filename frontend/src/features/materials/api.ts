import { apiUrl, request } from '../../shared/api'
import type { AnalysisPlan, Annotation, MaterialBatch, MaterialReport, MaterialSearchResult, SourceHit, SourcePassage } from './types'
const base = (id: string) => `/material-batches/${id}`
function parameters(values: Record<string,string|number|null|undefined>) {
  const params = new URLSearchParams()
  for (const [key,value] of Object.entries(values)) if(value!==null && value!==undefined && value!=='') params.set(key,String(value))
  return params.toString()
}
export const materialsApi = {
  create: (id: string, name: string, intro: string) => request<MaterialBatch>('/material-batches', {
    method: 'POST', body: JSON.stringify({request_id: id, name, intro}),
  }),
  get: (id: string) => request<MaterialBatch>(base(id)),
  save: (id: string, revision: number, name: string, intro: string, completeness: string) => request<MaterialBatch>(base(id), {
    method: 'PATCH', body: JSON.stringify({expected_revision: revision, name, intro, completeness}),
  }),
  upload: (batch: MaterialBatch, file: File, requestId: string) => request<MaterialBatch>(
    `${base(batch.id)}/files/${requestId}?filename=${encodeURIComponent(file.name)}&expected_revision=${batch.revision}`, {
      method: 'PUT', headers: {'Content-Type': 'application/octet-stream'}, body: file,
    }),
  annotate: (id: string, fileId: string, revision: number, annotations: Annotation[], included: boolean, textOnly: boolean) =>
    request<MaterialBatch>(`${base(id)}/files/${fileId}`, {method: 'PATCH', body: JSON.stringify({
      expected_revision: revision, annotations, included, text_only_accepted: textOnly,
    })}),
  retry: (id: string, fileId: string, revision: number) => request<MaterialBatch>(`${base(id)}/files/${fileId}/retry`, {
    method: 'POST', body: JSON.stringify({expected_revision: revision}),
  }),
  report: (id: string, fileId: string, processId: string, offset=0) => request<MaterialReport>(
    `${base(id)}/files/${fileId}/processes/${processId}?offset=${offset}&limit=30`),
  original: (id: string, fileId: string) => apiUrl(`${base(id)}/files/${fileId}/original`),
  artifact: (id: string, fileId: string, processId: string, name: string) => apiUrl(
    `${base(id)}/files/${fileId}/processes/${processId}/artifacts/${encodeURIComponent(name)}`),
  plan: (id: string) => request<AnalysisPlan>(`${base(id)}/analysis-plan`),
  analyze: (id: string, plan: AnalysisPlan) => request<MaterialBatch>(`${base(id)}/analyze`, {
    method: 'POST', body: JSON.stringify({expected_revision: plan.revision, routing_hash: plan.routing_hash}),
  }),
  reopen: (id: string, revision: number) => request<MaterialBatch>(`${base(id)}/reopen`, {
    method: 'POST', body: JSON.stringify({expected_revision: revision}),
  }),
  forCourse: (courseId: number, outlineId: number|null=null) => request<MaterialBatch | null>(`/material-batches/for-course/${courseId}?${parameters({outline_version_id:outlineId})}`),
  search: (courseId: number, outlineId: number|null, query: string, fileId: string, page: number|null, signal?: AbortSignal) =>
    request<MaterialSearchResult>(`/material-batches/for-course/${courseId}/search?${parameters({outline_version_id:outlineId,q:query,file_id:fileId,page})}`,{signal}),
  source: (courseId: number, outlineId: number|null, hit: SourceHit, offset=0, signal?: AbortSignal) =>
    request<SourcePassage>(`/material-batches/for-course/${courseId}/source?${parameters({outline_version_id:outlineId,file_id:hit.file_id,process_id:hit.process_id,element_id:hit.element_id,offset})}`,{signal}),
}
