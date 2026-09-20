// 数据结构与后端 courses/schemas.py 对应，组件统一从这里导入。
export type Point = { id: number; name: string; intro: string; content_markdown: string | null }
export type Section = { id: number; name: string; points: Point[] }
export type Chapter = { id: number; name: string; sections: Section[] }
export type Course = {
  id: number
  name: string
  intro: string
  outline_version_id: number | null
  directory_origin?: string | null
  intro_is_fallback?: boolean
  chapters: Chapter[]
}
export type CourseInput = Pick<Course, 'name' | 'intro'>
export type CourseTask = { label: string; chapterId?: number }
export type CourseSummary = {
  id: number
  name: string
  intro: string
  chapter_count: number
  section_count: number
  point_count: number
}

export function courseCounts(course: Course) {
  const sections = course.chapters.flatMap((chapter) => chapter.sections)
  return {
    chapters: course.chapters.length,
    sections: sections.length,
    points: sections.reduce((sum, section) => sum + section.points.length, 0),
  }
}

export function courseSummary(course: Course): CourseSummary {
  const counts = courseCounts(course)
  return {
    id: course.id,
    name: course.name,
    intro: course.intro,
    chapter_count: counts.chapters,
    section_count: counts.sections,
    point_count: counts.points,
  }
}
