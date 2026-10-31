"""Adapted from ownlight6/qmc-decoder (GPL-3.0) and tc_tea.
https://github.com/ownlight6/qmc-decoder
https://crates.io/crates/tc_tea
Task-local Python port; retain upstream attribution when redistributing.
"""
import base64, struct, math
import numpy as np
def tea_block(block,key):
    y,z=struct.unpack('>II',block);k=struct.unpack('>4I',key);s=0xe3779b90
    for _ in range(16):
        z=(z-(((y<<4)+k[2])^(y+s)^((y>>5)+k[3])))&0xffffffff
        y=(y-(((z<<4)+k[0])^(z+s)^((z>>5)+k[1])))&0xffffffff
        s=(s-0x9e3779b9)&0xffffffff
    return struct.pack('>II',y,z)

def xor(a,b):return bytes(x^y for x,y in zip(a,b))
def tea(data,key):
    if len(data)<16 or len(data)%8:raise ValueError('Invalid TEA block size')
    iv1=iv2=bytes(8);plain=bytearray()
    for pos in range(0,len(data),8):
        c=data[pos:pos+8];r=tea_block(xor(c,iv2),key)
        plain+=xor(r,iv1);iv1=c;iv2=r
    start=3+(plain[0]&7)
    if plain[-7:]!=bytes(7) or start>len(plain)-7:raise ValueError('TEA padding invalid')
    return bytes(plain[start:-7])

def parse_key(ekey):
    b=base64.b64decode(ekey)
    prefix=b'QQMusic EncV2,Key:'
    if b.startswith(prefix):
        b=base64.b64decode(tea(tea(b[len(prefix):],b'386ZJY!@#*$%^&)('),b'**#!(#$%&^a1cZ,T'))
    simple=bytes(min(255,int(100*abs(math.tan(float(np.float32(106)+np.float32(i)*np.float32(.1)))))) for i in range(8))
    key=bytes(v for pair in zip(simple,b[:8]) for v in pair)
    try:return b[:8]+tea(b[8:],key)
    except ValueError:return b

def decrypt(data,key,progress=None):
    out=bytearray(data);n=len(key)
    if not n:raise ValueError('Empty key')
    if progress:progress(0)
    if n<=300:
        for off in range(len(out)):
            if progress and off % 4096 == 0:progress(off/max(1,len(out)))
            p=off%0x7fff if off>0x7fff else off;j=(p*p+71214)%n;r=(j+4)&7
            out[off]^=((key[j]<<r)|(key[j]>>r))&255
        if progress:progress(1)
        return bytes(out)
    seed=[i&255 for i in range(n)];j=0
    for i in range(n):j=(j+seed[i]+key[i])%n;seed[i],seed[j]=seed[j],seed[i]
    h=1
    for v in key:
        if v:
            nxt=(h*v)&0xffffffff
            if nxt<=h:break
            h=nxt
    def segment(s,v):return int(h/((s+1)*v)*100) if v else 0xffffffffffffffff
    for i in range(min(128,len(out))):out[i]^=key[segment(i,key[i%n])%n]
    pos=128
    while pos<len(out):
        if progress:progress(pos/len(out))
        sid=pos//5120;end=min((sid+1)*5120,len(out));box=seed.copy();j=k=0
        skip=(segment(sid,key[sid&511])&511)+pos%5120
        for i in range(skip+end-pos):
            j=(j+1)%n;k=(box[j]+k)%n;box[j],box[k]=box[k],box[j]
            if i>=skip:out[pos+i-skip]^=box[(box[j]+box[k])%n]
        pos=end
    if progress:progress(1)
    return bytes(out)

