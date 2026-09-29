"""Student-side client. It carries a scoped classroom token, never provider keys."""
from __future__ import annotations
import httpx

class ServiceError(RuntimeError):
    pass

class PublicClient:
    def __init__(self,base_url:str,student_id:str,token:str):
        self.base_url=base_url.rstrip('/');self.student_id=student_id;self.token=token

    async def request(self,method:str,path:str,*,params=None,body=None,content=None,event_key=None,raw=False):
        headers={'Authorization':'Bearer '+self.token}
        if content is not None: headers['Content-Type']='audio/wav'
        if event_key: headers['Idempotency-Key']=event_key
        query={'student_id':self.student_id,**(params or {})}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(90,connect=8)) as c:
                response=await c.request(method,self.base_url+path,params=query,headers=headers,json=body,content=content)
            if response.status_code>=400:
                try: detail=response.json().get('detail','服务未完成请求')
                except ValueError: detail='服务未完成请求'
                raise ServiceError(f'公共服务返回 {response.status_code}：{detail}')
            return response.content if raw else response.json()
        except (httpx.HTTPError,ValueError) as exc:
            raise ServiceError('未能连接公共服务；本轮不能宣称已保存或已答对') from exc

    async def config(self): return await self.request('GET','/api/config')
    async def words(self,cfg):
        result=await self.request('GET','/api/words',params={k:cfg[k] for k in ('grade','semester','unit')})
        return result['words']
    async def progress(self): return await self.request('GET','/api/progress')
    async def record(self,word_id,status,unclear,key,evidence=None):
        body={'word_id':word_id,'status':status,'unclear':unclear}
        if evidence is not None: body['evidence']=evidence
        return await self.request('POST','/api/progress',body=body,event_key=key)
    async def chat(self,messages,json_output=True):
        return (await self.request('POST','/internal/chat',body={'messages':messages,'json_output':json_output}))['content']
    async def transcribe(self,wav,language):
        return await self.request('POST','/internal/asr',params={'language':language},content=wav)
    async def speak(self,segments,slow=False):
        return await self.request('POST','/internal/tts',body={'segments':segments,'slow':slow},raw=True)
