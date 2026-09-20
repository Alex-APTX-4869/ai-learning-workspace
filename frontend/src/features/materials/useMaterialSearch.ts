import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { errorMessage } from '../../shared/api'
import { materialsApi } from './api'
import type { MaterialSearchResult, SourceHit, SourcePassage } from './types'

export function useMaterialSearch(courseId: Ref<number>, outlineId: Ref<number|null>) {
  const result=ref<MaterialSearchResult|null>(null)
  const searching=ref(false), searchError=ref('')
  const selected=ref<SourceHit|null>(null), source=ref<SourcePassage|null>(null)
  const reading=ref(false), sourceError=ref('')
  let searchRevision=0, sourceRevision=0
  let searchController: AbortController|undefined, sourceController: AbortController|undefined
  function closeSource() {
    sourceRevision++; sourceController?.abort()
    selected.value=null; source.value=null; reading.value=false; sourceError.value=''
  }
  function reset() {
    searchRevision++; searchController?.abort()
    result.value=null; searching.value=false; searchError.value=''; closeSource()
  }
  async function search(query: string, fileId: string, page: number|null) {
    const revision=++searchRevision
    searchController?.abort(); searchController=new AbortController()
    closeSource(); result.value=null; searchError.value=''; searching.value=true
    try {
      const next=await materialsApi.search(courseId.value,outlineId.value,query,fileId,page,searchController.signal)
      if(revision===searchRevision) result.value=next
    } catch(error) { if(revision===searchRevision) searchError.value=errorMessage(error) }
    finally { if(revision===searchRevision) searching.value=false }
  }
  async function read(hit: SourceHit, offset=Math.max(0,hit.offset-250), append=false) {
    const revision=++sourceRevision
    sourceController?.abort(); sourceController=new AbortController()
    const previous=source.value
    // 只允许追加同一来源的连续下一段，避免不同结果拼接。
    const canAppend=append && selected.value===hit && previous?.next_offset===offset
    if(!canAppend) source.value=null
    selected.value=hit; sourceError.value=''; reading.value=true
    try {
      const next=await materialsApi.source(courseId.value,outlineId.value,hit,offset,sourceController.signal)
      if(revision===sourceRevision) source.value=canAppend && previous
        ? {...next,offset:previous.offset,text:previous.text+next.text} : next
    } catch(error) { if(revision===sourceRevision) sourceError.value=errorMessage(error) }
    finally { if(revision===sourceRevision) reading.value=false }
  }
  watch([courseId,outlineId],reset)
  onBeforeUnmount(reset)
  return {result,searching,searchError,selected,source,reading,sourceError,search,read,closeSource}
}
