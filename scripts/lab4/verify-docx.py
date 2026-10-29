from pathlib import Path
from zipfile import ZipFile
from lxml import etree
import json,sys
path=Path(sys.argv[1]);ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
with ZipFile(path) as z:
    root=etree.fromstring(z.read('word/document.xml'))
    visible=root.xpath('//w:r[w:t]',namespaces=ns)
    assert all(r.xpath('string(w:rPr/w:sz/@w:val)',namespaces=ns)=='28' for r in visible)
    assert all(r.xpath('string(w:rPr/w:rFonts/@w:ascii)',namespaces=ns)=='Times New Roman' for r in visible)
    assert not root.xpath('//w:del|//w:ins',namespaces=ns)
    captions=root.xpath('//w:p[w:pPr/w:pStyle[@w:val="Caption"]]',namespaces=ns)
    assert len(captions)==20,len(captions)
    settings=etree.fromstring(z.read('word/settings.xml'))
    assert settings.xpath('//w:doNotAutoCompressPictures',namespaces=ns)
    text=' '.join(root.xpath('//w:t/text()',namespaces=ns))
    assert 'Лабораторна робота 4' in text
    assert 'очікує SyncRep' in text
    print(json.dumps({'docx':path.name,'font':'Times New Roman','points':14,'figures':len(captions),'trackedChanges':False},ensure_ascii=False))
