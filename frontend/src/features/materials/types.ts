export interface Annotation {
  role: 'overview' | 'chapter' | 'reference' | 'auto'
  chapter: string
  note: string
  page_start: number | null
  page_end: number | null
}
export interface VisionAdoption {page:number;recognition_id:string;recognition_revision:number;result_hash:string}
export interface MaterialFile {
  batch_id?: string
  vision_pages?: VisionAdoption[]
  id: string; filename: string; suffix: string; byte_size: number; revision: number
  included: boolean; text_only_accepted: boolean; annotations: Annotation[]
  process_id: string | null; status: string; page_count: number | null
  element_count: number; issues: string[]; error: string | null
}
export interface MaterialContext {
  files: {file_id: string; filename: string; analysis: { summary: string; topics: string[]; gaps: string[] }}[]
  completeness: string
}
export interface MaterialBatch {
  id: string; name: string; intro: string; completeness: 'partial' | 'complete'
  revision: number; status: string; error: string | null; intake_id: number | null
  files: MaterialFile[]; context: MaterialContext | null
  analysis_completed_steps: number; analysis_provider: string | null
}
export interface AnalysisPlan {
  vision_page_count?: number
  revision: number; file_count: number; parts: number; maximum_calls: number
  provider_name: string; model: string; routing_hash: string
  intake_providers: string[]
}
export interface Locator { type: string; page?: number; paragraph?: number; table?: number; heading_path?: string[]; source_kind?: string; recognition_id?: string; recognition_revision?: number }
export interface MaterialReport {
  elements: { id: string; kind: string; text: string; locator: Locator; preview?: string }[]
  element_count: number
  artifacts: {path: string; locator: Locator}[]
  issues: {code: string; locator: Locator | null}[]
}

export interface SourceHit {
  batch_id: string; file_id: string; process_id: string; element_id: string
  filename: string; locator: Locator; offset: number; excerpt: string; text_only: boolean
}
export interface MaterialSearchResult {
  method: 'keyword'; hits: SourceHit[]; total: number
  scope_available: boolean; outline_version_id: number | null
}
export interface SourcePassage extends Omit<SourceHit, 'excerpt'> {
  text: string; total_characters: number; next_offset: number | null; preview: string | null
}
