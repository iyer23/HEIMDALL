import { useState, useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import toast from 'react-hot-toast';
import { Upload, X, Loader2, FlaskConical, FileImage, User, ScanLine, Check, AlertTriangle, Camera } from 'lucide-react';
import { runScreening, runDemoScreening } from '@/services/api';
import type { DemoCase } from '@/types';
import { formatFileSize, validateFile } from '@/utils';
import { DocScanArt } from '@/components/art/Art';

const DEMO_CASES: { id: DemoCase; label: string; expected: string; color: string; group: string }[] = [
  { id:'valid_passport',   label:'Valid Passport',    expected:'Pass',        color:'#356859', group:'Passport' },
  { id:'expired_document', label:'Expired Passport',  expected:'Blocked',     color:'#B54848', group:'Passport' },
  { id:'tampered_text',    label:'Tampered Passport', expected:'High Risk',   color:'#B54848', group:'Passport' },
  { id:'face_mismatch',    label:'Face Mismatch',     expected:'High Risk',   color:'#B54848', group:'Passport' },
  { id:'multiple_flags',   label:'Multiple Flags',    expected:'High Risk',   color:'#B54848', group:'Visa'     },
  { id:'aadhaar_valid',    label:'Valid Aadhaar',      expected:'Pass',        color:'#356859', group:'Aadhaar'  },
  { id:'aadhaar_tampered', label:'Tampered Aadhaar',  expected:'High Risk',   color:'#B54848', group:'Aadhaar'  },
];

const STEPS = [
  'Uploading document…',
  'Detecting document type…',
  'Extracting fields (OCR)…',
  'Validating document rules…',
  'Parsing & verifying MRZ…',
  'Analysing image integrity…',
  'Verifying face…',
  'Evidence Fusion Engine…',
];

type Tab = 'upload' | 'demo';

export default function NewScreeningPage() {
  const navigate = useNavigate();
  const [tab, setTab]             = useState<Tab>('upload');
  const [docFile, setDocFile]     = useState<File | null>(null);
  const [personFile, setPerson]   = useState<File | null>(null);
  const [preview, setPreview]     = useState<string | null>(null);
  const [running, setRunning]     = useState(false);
  const [stepIdx, setStepIdx]     = useState(-1);
  const [demoCase, setDemoCase]   = useState<DemoCase>('valid_passport');

  // ── Camera capture ──
  const [camTarget, setCamTarget] = useState<'doc' | 'person' | null>(null);
  const videoRef  = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    if (!camTarget) return;
    navigator.mediaDevices
      ?.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1920 } } })
      .then(s => {
        streamRef.current = s;
        if (videoRef.current) videoRef.current.srcObject = s;
      })
      .catch(() => { toast.error('Camera unavailable or permission denied.'); setCamTarget(null); });
    return () => {
      streamRef.current?.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    };
  }, [camTarget]);

  const capture = () => {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext('2d')!.drawImage(v, 0, 0);
    canvas.toBlob(b => {
      if (!b) return;
      const f = new File([b], `camera_capture_${Date.now()}.jpg`, { type: 'image/jpeg' });
      if (camTarget === 'doc') { setDocFile(f); setPreview(URL.createObjectURL(f)); }
      else setPerson(f);
      toast.success('Photo captured.');
      setCamTarget(null);
    }, 'image/jpeg', 0.95);
  };

  const runSteps = async () => {
    const times = [300, 400, 1200, 500, 800, 1800, 900, 400];
    for (let i = 0; i < STEPS.length; i++) {
      setStepIdx(i);
      await new Promise(r => setTimeout(r, times[i]));
    }
  };

  const onDrop = useCallback((files: File[]) => {
    const f = files[0]; if (!f) return;
    const err = validateFile(f); if (err) { toast.error(err); return; }
    setDocFile(f);
    if (f.type.startsWith('image/')) setPreview(URL.createObjectURL(f));
  }, []);
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { 'image/jpeg':[], 'image/png':[], 'application/pdf':[] }, maxFiles:1, disabled:running,
  });

  const onDropPerson = useCallback((files: File[]) => {
    const f = files[0]; if (!f) return;
    const err = validateFile(f); if (err) { toast.error(err); return; }
    setPerson(f);
  }, []);
  const { getRootProps: getPProps, getInputProps: getPInput } = useDropzone({
    onDrop: onDropPerson, accept: { 'image/jpeg':[], 'image/png':[] }, maxFiles:1, disabled:running,
  });

  const go = async () => {
    setRunning(true); setStepIdx(0);
    try {
      const fn = tab === 'demo'
        ? runDemoScreening(demoCase)
        : runScreening({ documentFile: docFile!, personFile });
      const [result] = await Promise.all([fn, runSteps()]);
      navigate(`/screening/${result.screening_id}`, { state: { result } });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Screening failed — check backend.');
      setRunning(false); setStepIdx(-1);
    }
  };

  const groups = ['Passport', 'Visa', 'Aadhaar'];

  return (
    <div className="max-w-[860px]">
      {/* Warning */}
      <div className="rise mb-5 flex items-start gap-2.5 rounded-lg border border-warn/25 bg-warn/[0.07] px-4 py-2.5 text-xs leading-relaxed text-warn/90">
        <AlertTriangle size={14} className="mt-0.5 shrink-0 text-warn" />
        <span><strong className="font-semibold text-warn">Note:</strong> Use test or demo documents only. Do not upload real personal identity documents unless authorised.</span>
      </div>

      {/* Tabs */}
      <div className="tabbar rise rise-1 mb-5">
        {(['upload','demo'] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            disabled={running}
            className={`tab inline-flex items-center gap-2 ${tab === t ? 'tab-active' : ''}`}
          >
            {t === 'upload' ? <FileImage size={14} /> : <FlaskConical size={14} />}
            {t === 'upload' ? 'Upload Document' : 'Demo Mode'}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[1fr_280px]">
        {/* Left */}
        <div className="flex flex-col gap-4">
          {tab === 'upload' ? (
            <>
              {/* Document */}
              <div className="panel rise rise-2 p-5">
                <div className="mb-3 flex items-center gap-2">
                  <ScanLine size={14} className="text-vigil-400" />
                  <span className="panel-title">Identity Document</span>
                  <span className="text-bad">*</span>
                </div>
                {docFile ? (
                  <div className="flex items-center gap-3 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2.5">
                    {preview && <img src={preview} alt="" className="h-9 w-14 rounded border border-white/10 object-cover" />}
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13px] font-medium text-white">{docFile.name}</div>
                      <div className="font-mono text-[11px] text-mist-dim">{formatFileSize(docFile.size)}</div>
                    </div>
                    {!running && (
                      <button onClick={() => { setDocFile(null); setPreview(null); }} className="rounded p-1.5 text-mist-dim transition-colors hover:bg-white/[0.06] hover:text-bad">
                        <X size={15} />
                      </button>
                    )}
                  </div>
                ) : (
                  <div
                    {...getRootProps()}
                    className={`relative cursor-pointer overflow-hidden rounded-lg border-2 border-dashed px-4 py-9 text-center transition-all duration-150 ${
                      isDragActive
                        ? 'border-vigil-400 bg-vigil-400/[0.07]'
                        : 'border-white/[0.12] bg-white/[0.02] hover:border-vigil-400/50 hover:bg-white/[0.04]'
                    }`}
                  >
                    <input {...getInputProps()} />
                    {isDragActive && (
                      <span className="scan-sweep pointer-events-none absolute inset-y-0 left-0 w-1/3 bg-gradient-to-r from-transparent via-vigil-400/10 to-transparent" />
                    )}
                    <div className="pointer-events-none mb-2.5 flex justify-center text-[#3F4A32]">
                      <DocScanArt size={88} />
                    </div>
                    <div className="text-[13px] font-medium text-[#1F2420]">{isDragActive ? 'Drop here' : 'Drag & drop or click to browse'}</div>
                    <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-[#8A9080]">JPG · PNG · PDF · max 10 MB</div>
                    <button
                      type="button"
                      onClick={e => { e.stopPropagation(); setCamTarget('doc'); }}
                      className="btn-ghost mt-3 !rounded-lg !px-3 !py-1.5 text-xs"
                    >
                      <Camera size={13} /> Use camera
                    </button>
                  </div>
                )}
              </div>
              {/* Person photo */}
              <div className="panel rise rise-3 p-5">
                <div className="mb-3 flex items-center gap-2">
                  <User size={14} className="text-mist" />
                  <span className="panel-title">Person Photo</span>
                  <span className="text-[11px] text-mist-dim">(optional — face verification)</span>
                </div>
                {personFile ? (
                  <div className="flex items-center gap-3 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2.5">
                    <div className="flex-1 text-[13px] text-white">{personFile.name}</div>
                    {!running && (
                      <button onClick={() => setPerson(null)} className="rounded p-1.5 text-mist-dim transition-colors hover:bg-white/[0.06] hover:text-bad">
                        <X size={14} />
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2.5">
                    <div
                      {...getPProps()}
                      className="cursor-pointer rounded-lg border-2 border-dashed border-white/[0.12] bg-white/[0.02] px-4 py-5 text-center text-xs text-mist transition-all duration-150 hover:border-vigil-400/50 hover:bg-white/[0.04] hover:text-mist-bright"
                    >
                      <input {...getPInput()} />
                      Click to upload checkpoint photo
                    </div>
                    <button
                      type="button"
                      onClick={() => setCamTarget('person')}
                      className="rounded-lg border-2 border-dashed border-white/[0.12] bg-white/[0.02] px-4 py-5 text-center text-xs text-mist transition-all duration-150 hover:border-vigil-400/50 hover:bg-white/[0.04] hover:text-mist-bright"
                    >
                      <span className="flex items-center justify-center gap-2"><Camera size={15} /> Capture with camera</span>
                    </button>
                  </div>
                )}
              </div>
            </>
          ) : (
            /* Demo Mode */
            <div className="panel rise rise-2 p-5">
              <div className="mb-1 flex items-center gap-2">
                <FlaskConical size={14} className="text-vigil-400" />
                <span className="panel-title">Select a Test Case</span>
              </div>
              <div className="mb-4 text-xs text-mist-dim">
                Pre-configured synthetic cases — labelled <strong className="text-fuchsia-300">DEMO</strong> in results.
              </div>
              {groups.map(g => (
                <div key={g} className="mb-4 last:mb-0">
                  <div className="eyebrow mb-2">{g === 'Aadhaar' ? '🇮🇳 ' : ''}{g}</div>
                  <div className="space-y-1.5">
                    {DEMO_CASES.filter(c => c.group === g).map(c => (
                      <label
                        key={c.id}
                        className={`flex cursor-pointer items-center justify-between rounded-lg border px-3.5 py-2.5 transition-all duration-150 ${
                          demoCase === c.id
                            ? 'border-vigil-400/50 bg-vigil-400/[0.08]'
                            : 'border-white/[0.07] bg-white/[0.02] hover:border-white/[0.15] hover:bg-white/[0.04]'
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <span
                            className={`flex h-4 w-4 items-center justify-center rounded-full border transition-colors ${
                              demoCase === c.id ? 'border-vigil-400 bg-vigil-400' : 'border-mist-dim'
                            }`}
                          >
                            {demoCase === c.id && <Check size={10} strokeWidth={3.5} className="text-ink-950" />}
                          </span>
                          <input type="radio" value={c.id} checked={demoCase === c.id} onChange={() => setDemoCase(c.id)} disabled={running} className="sr-only" />
                          <span className="text-[13px] font-medium text-white">{c.label}</span>
                        </div>
                        <span
                          className="rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider"
                          style={{ background: `${c.color}1a`, color: c.color }}
                        >
                          {c.expected}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Run button */}
          <button
            onClick={go}
            disabled={running || (tab === 'upload' && !docFile)}
            className="btn-primary rise rise-4 w-full py-3 text-[15px]"
          >
            {running
              ? <><Loader2 size={16} className="animate-spin" />Analysing…</>
              : <><ScanLine size={16} />Run Screening</>}
          </button>
        </div>

        {/* Right: pipeline steps */}
        <div className="panel rise rise-3 p-5">
          <div className="panel-title mb-5">Analysis Pipeline</div>
          <div className="relative">
            <span className="absolute bottom-2 left-[10px] top-2 w-px bg-white/[0.07]" />
            {STEPS.map((s, i) => {
              const done    = running && i < stepIdx;
              const current = running && i === stepIdx;
              return (
                <div key={s} className="relative mb-4 flex items-center gap-3 last:mb-0">
                  <div
                    className={`z-10 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold transition-all duration-200 ${
                      done
                        ? 'bg-ok/20 text-ok ring-1 ring-ok/40'
                        : current
                          ? 'bg-vigil-400/20 text-vigil-300 ring-2 ring-vigil-400/60'
                          : 'bg-ink-800 text-mist-dim ring-1 ring-white/[0.08]'
                    }`}
                  >
                    {done ? <Check size={11} strokeWidth={3} /> : i + 1}
                  </div>
                  <span
                    className={`text-xs leading-snug transition-colors duration-200 ${
                      done ? 'text-mist' : current ? 'font-semibold text-vigil-300' : 'text-mist-dim'
                    }`}
                  >
                    {s}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      {/* ── Camera modal ── */}
      {camTarget && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4 backdrop-blur-md"
          onClick={() => setCamTarget(null)}
        >
          <div
            className="panel w-full max-w-lg overflow-hidden !p-0"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-white/[0.07] px-4 py-3">
              <span className="panel-title">{camTarget === 'doc' ? 'Capture Document' : 'Capture Photo'}</span>
              <button onClick={() => setCamTarget(null)} className="rounded-lg p-1.5 text-mist transition-colors hover:bg-white/[0.07] hover:text-white">
                <X size={16} />
              </button>
            </div>
            <div className="relative bg-black">
              <video ref={videoRef} autoPlay playsInline muted className="aspect-[4/3] w-full object-cover" />
              <div className="pointer-events-none absolute inset-5 rounded-lg border border-vigil-400/40 shadow-[0_0_28px_rgba(45,212,191,0.15)_inset]" />
            </div>
            <div className="flex justify-center gap-3 px-4 py-4">
              <button onClick={capture} className="btn-primary min-w-[150px]">
                <Camera size={15} /> Capture
              </button>
              <button onClick={() => setCamTarget(null)} className="btn-ghost">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
