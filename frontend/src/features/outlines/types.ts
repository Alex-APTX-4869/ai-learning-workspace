export type OutlineSection = {
  name: string
}

export type OutlineChapter = {
  name: string
  sections: OutlineSection[]
}

export type OutlineSnapshot = {
  name: string
  chapters: OutlineChapter[]
}

export type OutlineVersion = {
  id: number
  course_id: number
  version_number: number
  name: string
  outline: OutlineSnapshot
  additional_requirements: string | null
  reference_version_id: number | null
  created_at: string
  selected: boolean
}

export type OutlineGenerationInput = {
  additional_requirements?: string
  reference_version_id?: number | null
}

export type OutlineActivation = {
  version: OutlineVersion
  course: import('../courses/types').Course
}

export type OutlineStreamEvent =
  | { type: 'start' }
  | { type: 'chapter'; chapter: { index: number; name: string } }
  | {
      type: 'section'
      section: { chapter_index: number; index: number; name: string }
    }
  | { type: 'completed'; version: OutlineVersion }
  | { type: 'error'; detail: string }
