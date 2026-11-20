"""Evidence extraction for files admitted through the local upload vault."""
import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import PurePath

MAX_BYTES=10*1024*1024
MAX_ROWS=5000
EXTENSIONS={".csv",".json",".pdf",".xlsx"}
ADMITTED={"VALID","PARTIAL"}

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

def read_rows(type_, data):
    if type_==".csv":
        reader=csv.DictReader(io.StringIO(data.decode("utf-8-sig"),newline=""),strict=True)
        fields=reader.fieldnames
        if not fields or not all(x.strip() for x in fields) or len(set(fields))!=len(fields):
            raise ValueError("CSV requires unique, nonempty column headers")
        for num,value in enumerate(reader,2):
            if None in value or None in value.values():
                fields={str(k):v for k,v in value.items() if k is not None}
                if None in value:fields["_extra_values"]=value[None]
                yield str(num),fields,"Invalid CSV column count"
            else:
                yield str(num),value,None
    elif type_==".json":
        file=json.loads(data.decode("utf-8-sig"))
        if isinstance(file,dict):
            arrays=[k for k,v in file.items() if isinstance(v,list)]
            if len(arrays)==1:
                key=arrays[0]
                metadata={k:v for k,v in file.items() if k!=key}
                if metadata:yield "metadata",metadata,None
                for num,value in enumerate(file[key]):
                    yield f"{key}[{num}]",value,None
                return
            items=[file]
        elif isinstance(file,list):items=file
        else:raise ValueError("JSON requires objects or an array of objects")
        for num,value in enumerate(items):
            yield str(num),value,None
    elif type_==".pdf":
        from pypdf import PdfReader
        pdf=PdfReader(io.BytesIO(data),strict=False)
        if pdf.is_encrypted:raise ValueError("Encrypted PDF requires a readable copy for review")
        for page,content in enumerate(pdf.pages,1):
            try:
                yield "p"+str(page),{"text":content.extract_text() or ""},None
            except Exception as exc:
                yield "p"+str(page),None,"Page extraction failed ("+type(exc).__name__+")"
    elif type_==".xlsx":
        from openpyxl import load_workbook
        if len(data)<4 or data[:2]!=b"PK":raise ValueError("XLSX must be a spreadsheet archive")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(x.file_size for x in archive.infolist())>48*1024*1024:
                raise ValueError("Expanded workbook exceeds the parsing limit")
        book=load_workbook(io.BytesIO(data),read_only=True,data_only=True,keep_links=False)
        try:
            for sheet in book:
                if (sheet.max_column or 0)>256:raise ValueError("Workbook sheet exceeds 256 columns")
                header=None
                for num,row in enumerate(sheet.iter_rows(values_only=True),1):
                    if num==1:
                        normalized=[v.strip() if isinstance(v,str) else "" for v in row]
                        if all(normalized) and len(normalized)==len({v.casefold() for v in normalized}):
                            header=normalized
                            yield f"{sheet.title}!{num}",{"header":normalized},None
                            continue
                    raw=dict(zip(header,row)) if header else {f"column_{i}":v for i,v in enumerate(row,1)}
                    yield f"{sheet.title}!{num}",raw,None
        finally:book.close()

def normalize(locator,raw,error,seen,type_):
    state,reason="VALID","Structured record has a usable timestamp"
    utc,original=None,None
    if error or not isinstance(raw,dict):
        state,reason="REJECTED",error or "Expected a record object"
        raw={"value":raw}
    elif not any(v is not None and v!="" for v in raw.values()):
        state,reason="QUARANTINED","No extractable values. A scanned PDF may require manual transcription."
    else:
        names={k.casefold():v for k,v in raw.items()}
        original=next((names[k] for k in ("timestamp","ts_utc","time","event_time","utc") if k in names),None)
        if original is None:
            state,reason="PARTIAL","Record retained for review without a normalized event time"
        else:
            try:
                dt=datetime.fromisoformat(str(original).replace("Z","+00:00"))
                if dt.tzinfo is None:
                    state,reason="AMBIGUOUS","Timestamp offset is missing"
                else:utc=dt.astimezone(timezone.utc).isoformat(timespec="microseconds")
            except ValueError:
                state,reason="QUARANTINED","Timestamp could not be interpreted as ISO 8601"
        key=hashlib.sha256(json.dumps(raw,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()
        if key in seen and state in ADMITTED:
            state,reason="DUPLICATE","Same record values as "+seen[key]
        else:seen.setdefault(key,locator)
    return dict(locator=locator,status=state,reason=reason,utc=utc,original=original,raw=raw,
                type={".pdf":"Document page",".xlsx":"Spreadsheet row"}.get(type_,"Structured record"))

def extract(filename,data):
    suffix=PurePath(filename).suffix.lower()
    if suffix not in EXTENSIONS:return [],"Supported extensions are CSV, JSON, PDF and XLSX"
    records,seen=[],{}
    error=""
    try:
        for position,(locator,raw,issue) in enumerate(read_rows(suffix,data)):
            if position>=MAX_ROWS:
                error="Extraction limit reached. Original is retained in full. Unindexed rows require review."
                break
            records.append(normalize(locator,raw,issue,seen,suffix))
        if not records and not error:error="No extractable records"
    except Exception as exc:
        error=f"Parsing stopped ({type(exc).__name__}): {str(exc)[:300]}"
    return records,error
