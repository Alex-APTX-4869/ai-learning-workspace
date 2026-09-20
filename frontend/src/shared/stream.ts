import { apiUrl, httpErrorFromResponse } from './api'

export async function streamMarkdown(path: string, signal: AbortSignal, onDelta: (text: string) => void) {
  const response = await fetch(apiUrl(path), {method:'POST',signal,headers:{Accept:'application/x-ndjson'}})
  if (!response.ok) throw await httpErrorFromResponse(response)
  if (!response.body) throw new Error('当前浏览器无法接收流式解释。')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer='', completed=false
  function consume(line: string) {
    if (!line.trim()) return
    if (completed) throw new Error('流式解释协议异常。')
    const event=JSON.parse(line)
    if(event.type==='delta' && typeof event.text==='string') onDelta(event.text)
    else if(event.type==='done') completed=true
    else if(event.type==='error') throw new Error(event.message || '解释中断，请重试。')
    else throw new Error('无法识别解释内容。')
  }
  try {
    for (;;) {
      const {done,value}=await reader.read()
      buffer+=decoder.decode(value,{stream:!done})
      let newline
      while((newline=buffer.indexOf('\n'))>=0) {consume(buffer.slice(0,newline));buffer=buffer.slice(newline+1)}
      if(buffer.length>100000) throw new Error('解释内容超出接收范围。')
      if(done)break
    }
    consume(buffer)
    if(!completed) throw new Error('连接中断，以下解释尚未完成，请重试。')
  } finally {await reader.cancel().catch(()=>{});reader.releaseLock()}
}
