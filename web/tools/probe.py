import sys, numpy as np
from PIL import Image
from scipy import ndimage as ndi
G='/Users/keonamid/archil-playground/ui/gemini/'
def comps(fn, dil=12):
    im=np.asarray(Image.open(G+fn).convert('RGB')).astype(int)
    R,Gc,B=im[...,0],im[...,1],im[...,2]
    mag=(R>140)&(B>140)&(Gc<120)
    op=~mag
    op=ndi.binary_erosion(op,iterations=2)
    d=ndi.binary_dilation(op,iterations=dil)
    lab,n=ndi.label(d)
    out=[]
    for i,sl in enumerate(ndi.find_objects(lab),1):
        m=(lab[sl]==i)&op[sl]
        if m.sum()<150: continue
        ys,xs=np.nonzero(m)
        y0=sl[0].start+ys.min(); y1=sl[0].start+ys.max()+1; x0=sl[1].start+xs.min(); x1=sl[1].start+xs.max()+1
        out.append((x0,y0,x1,y1,int(m.sum())))
    out.sort(key=lambda b:(round(b[1]/120),b[0]))
    print(fn, im.shape, len(out))
    for b in out: print('  x %4d-%4d  y %4d-%4d  w %3d h %3d  area %6d   disp(%d,%d)'%(b[0],b[2],b[1],b[3],b[2]-b[0],b[3]-b[1],b[4],(b[0]+b[2])/2/1.376,(b[1]+b[3])/2/1.376))
for fn in sys.argv[1:]: comps(fn)
