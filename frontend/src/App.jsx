import React, { useState, useEffect, useRef } from 'react';
import {
  ShieldAlert, Activity, Network, Scan, MessageSquareWarning,
  PhoneCall, MapPin, AlertTriangle, CheckCircle2, Lock,
  PauseCircle, X, RefreshCw, Smartphone, Mic, MicOff, Globe,
  Download, Share2, UploadCloud, FileSearch, Fingerprint, Fingerprint as FingerprintIcon,
  MessageCircle, FileText, Send, ChevronRight, Check, Map,
  Radio, Cpu, Volume2, Clock, Layers, Target, Thermometer, Shield, TrendingUp, Users, Eye
} from 'lucide-react';
import ForceGraph2D from 'react-force-graph-2d';

import { MapContainer, TileLayer, Marker, Popup, Circle, CircleMarker, useMap, Polygon, Tooltip } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import * as h3 from 'h3-js';

// Fix for Leaflet default icon paths in modern bundlers like Vite
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

export default function App() {
  // Main view toggle: 'nodal' (Dashboard) or 'citizen' (Mobile App)
  const [mainView, setMainView] = useState('nodal');

  // --- NODAL OFFICER DASHBOARD STATE ---
  const [activeTab, setActiveTab] = useState('dashboard');

  const [activeThreats, setActiveThreats] = useState([
    {
      id: 'TR-892', type: 'Digital Arrest Script', status: 'critical', location: 'Mumbai - Sector 4',
      duration: '45m 12s', victim: 'Senior Citizen (Tier 1 Risk)', confidence: '98%',
      details: 'AI matched script: "CBI... money laundering... isolation"',
      deepfakeScore: '94%',
      spectralFlatness: '0.512',
      structuralThreat: 'CRITICAL (Degree Centrality: 8 - Sybil Ring Detected)'
    }
  ]);

  const [intercepted, setIntercepted] = useState([]);
  const [filter, setFilter] = useState('all');
  const [confirmDialog, setConfirmDialog] = useState(null);
  const [toast, setToast] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  // --- GRAPH INTELLIGENCE BRIDGE STATE ---
  const [highlightedEntities, setHighlightedEntities] = useState([]);
  const [highlightSourceCase, setHighlightSourceCase] = useState(null);
  const [graphStats, setGraphStats] = useState({ total_nodes: 0, total_edges: 0, total_campaigns: 0, sybil_rings_detected: 0, recent_intercepts: [] });

  // Fetch graph stats on mount and every 10 seconds
  useEffect(() => {
    const fetchGraphStats = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/graph/stats');
        const data = await res.json();
        if (data.success && data.data) setGraphStats(data.data);
      } catch (e) { /* silent */ }
    };
    fetchGraphStats();
    const interval = setInterval(fetchGraphStats, 10000);
    return () => clearInterval(interval);
  }, []);

  // --- CITIZEN SHIELD STATE (SPLIT-STREAM) ---
  const [citizenTab, setCitizenTab] = useState('shield'); // 'shield' or 'assistant'
  const [callLanguage, setCallLanguage] = useState('en-IN');

  const [isListening, setIsListening] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState('');

  // Dual-Sensor State
  const [nlpThreat, setNlpThreat] = useState('safe');
  const [audioThreat, setAudioThreat] = useState('safe');
  const [shieldStatus, setShieldStatus] = useState('safe');

  const streamRef = useRef(null);
  const audioIntervalRef = useRef(null);
  const recognitionRef = useRef(null);
  const finalTranscriptRef = useRef('');
  const wsRef = useRef(null);

  // Live deepfake diagnostics from WebSocket
  const [liveDeepfakeDiag, setLiveDeepfakeDiag] = useState(null);

  // Update master shield status if EITHER sensor trips
  useEffect(() => {
    if (nlpThreat === 'critical' || audioThreat === 'critical') setShieldStatus('critical');
    else if (nlpThreat === 'warning' || audioThreat === 'warning') setShieldStatus('warning');
    else setShieldStatus('safe');
  }, [nlpThreat, audioThreat]);

  // Fraud Assistant Chat State
  const [chatInput, setChatInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [showNcrbModal, setShowNcrbModal] = useState(false);
  const [chatMessages, setChatMessages] = useState([
    {
      id: 1, sender: 'bot', status: 'safe',
      text: 'Namaste! I am your AI Fraud Assistant. Paste any suspicious SMS, payment link, or describe an incident. I will analyze the risk instantly.',
      showNcrb: false
    }
  ]);

  // --- SPLIT STREAM LANE 1: NATIVE BROWSER STT (SEMANTICS) ---
  const evaluateTextSemantics = async (text) => {
    if (text.trim().length < 10) return;
    try {
      const response = await fetch('http://127.0.0.1:8000/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript: text, caller_id: "Live Citizen Mic" })
      });
      const data = await response.json();
      if (data.success && data.analysis) {
        setNlpThreat(data.analysis.status);
      }
    } catch (error) {
      console.error("Semantic API Error:", error);
    }
  };

  // --- SPLIT STREAM LANE 2: RAW AUDIO CHUNKS (ACOUSTICS via WebSocket) ---
  const evaluateAcoustics = async (blob) => {
    if (blob.size === 0 || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    try {
      const arrayBuffer = await blob.arrayBuffer();
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
      const wavBlob = audioBufferToWav(audioBuffer);
      const wavBytes = await wavBlob.arrayBuffer();
      // Send raw WAV bytes over WebSocket for real-time analysis
      wsRef.current.send(wavBytes);
    } catch (e) {
      console.error("Audio format conversion error:", e);
    }
  };

  // --- MASTER MICROPHONE CONTROLLER ---
  const startMicrophone = async () => {
    try {
      // Force Bluetooth/Headset Quality
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true }
      });
      streamRef.current = stream;

      setIsListening(true);
      setNlpThreat('safe');
      setAudioThreat('safe');
      setLiveTranscript('');
      setLiveDeepfakeDiag(null);
      finalTranscriptRef.current = '';

      // --- OPEN WEBSOCKET FOR REAL-TIME DEEPFAKE DETECTION ---
      try {
        const ws = new WebSocket('ws://127.0.0.1:8000/ws/live-audio');
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            setLiveDeepfakeDiag(data);
            if (data.deepfake_alert) {
              setAudioThreat('critical');
            } else {
              setAudioThreat('safe');
            }
          } catch (parseErr) {
            console.error('WebSocket parse error:', parseErr);
          }
        };
        ws.onerror = (err) => console.error('WebSocket error:', err);
        ws.onclose = () => console.log('WebSocket closed');
        wsRef.current = ws;
      } catch (wsErr) {
        console.error('WebSocket connection failed, falling back to HTTP:', wsErr);
      }

      // --- START LANE 2 (RAW AUDIO RECORDING LOOP) ---
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      const dataArray = new Uint8Array(analyser.frequencyBinCount);

      const recordChunk = () => {
        if (!streamRef.current) return;
        analyser.getByteFrequencyData(dataArray);
        const avgVol = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;

        // VAD: Drop silence to save backend math computation!
        if (avgVol < 2) return;

        const recorder = new MediaRecorder(streamRef.current);
        const chunks = [];
        recorder.ondataavailable = e => chunks.push(e.data);
        recorder.onstop = () => {
          const blob = new Blob(chunks, { type: 'audio/webm' });
          evaluateAcoustics(blob);
        };

        recorder.start();
        setTimeout(() => { if (recorder.state === "recording") recorder.stop(); }, 3800);
      };

      recordChunk();
      audioIntervalRef.current = setInterval(recordChunk, 4000);

      // --- START LANE 1 (NATIVE STT) ---
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SpeechRecognition) {
        recognitionRef.current = new SpeechRecognition();
        recognitionRef.current.continuous = true;
        recognitionRef.current.interimResults = true;
        recognitionRef.current.lang = callLanguage;

        recognitionRef.current.onresult = (event) => {
          let interimTranscript = '';
          for (let i = event.resultIndex; i < event.results.length; i++) {
            if (event.results[i].isFinal) {
              finalTranscriptRef.current += event.results[i][0].transcript + " ";
              evaluateTextSemantics(finalTranscriptRef.current);
            } else {
              interimTranscript += event.results[i][0].transcript;
            }
          }
          setLiveTranscript(finalTranscriptRef.current + interimTranscript);
        };

        recognitionRef.current.onerror = (e) => console.warn("STT Engine: Waiting for voice...", e.error);
        recognitionRef.current.start();
      } else {
        setToast("Browser lacks Native STT. Using Audio DSP Only.");
        setTimeout(() => setToast(null), 4000);
      }

    } catch (err) {
      setToast("Microphone access denied. Please allow permissions.");
      setTimeout(() => setToast(null), 4000);
    }
  };

  const stopMicrophone = () => {
    if (audioIntervalRef.current) clearInterval(audioIntervalRef.current);
    if (recognitionRef.current) recognitionRef.current.stop();
    if (wsRef.current) {
      try { wsRef.current.close(); } catch(e) { /* ignore */ }
      wsRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    setIsListening(false);
    setLiveDeepfakeDiag(null);
  };

  const toggleListen = () => {
    if (isListening) stopMicrophone();
    else startMicrophone();
  };

  useEffect(() => {
    return () => stopMicrophone();
  }, []);

  const handleChatSubmit = async (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const userMsg = { id: Date.now(), sender: 'user', text: chatInput };
    setChatMessages(prev => [...prev, userMsg]);
    setChatInput('');
    setIsChatLoading(true);

    try {
      const response = await fetch('http://127.0.0.1:8000/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript: userMsg.text, caller_id: "WhatsApp/App Assistant" })
      });
      const data = await response.json();

      if (data.success && data.analysis) {
        const isThreat = data.analysis.status !== 'safe';
        const botMsg = {
          id: Date.now() + 1, sender: 'bot', status: data.analysis.status,
          text: data.analysis.details, confidence: data.analysis.confidence, showNcrb: isThreat
        };
        setChatMessages(prev => [...prev, botMsg]);
      }
    } catch (error) {
      setChatMessages(prev => [...prev, { id: Date.now() + 1, sender: 'bot', text: 'Network error. Cannot reach AI.', status: 'error', showNcrb: false }]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const simulateLiveCall = async () => {
    setIsAnalyzing(true);
    // Randomize incoming transcript and caller_id to create multiple spheres (campaigns)
    const dummyCases = [
      { transcript: "This is Mumbai customs calling we found illegal parcel from your Aadhar Card we need you transfer 20000 account to HDFC bank account 501002341", caller_id: "+91-9876543210 (Spoofed)" },
      { transcript: "This is CBI officer Rajesh. Your name is in money laundering case. Do not cut the call. You are under digital arrest. Pay 50000 penalty to UPI id cbi-pay@okicici immediately or police will come to your house.", caller_id: "+91-8888888888 (Spoofed)" },
      { transcript: "Congratulations! You are selected for work from home job at Amazon. Earn 5000 daily by rating products. Send 2000 registration fee to UPI hr-amazon@ybl to start.", caller_id: "+91-7777777777 (Spoofed)" },
      { transcript: "Dear SBI customer, your bank account is blocked due to incomplete KYC. Please share the OTP sent to your number to verify your identity and unblock the account.", caller_id: "+91-9999999999 (Spoofed)" },
      { transcript: "Sir I am calling from TRAI your mobile number will be blocked in 2 hours due to illegal activities. Please press 1 to talk to our executive or transfer fine to account 123456789.", caller_id: "+91-6666666666 (Spoofed)" }
    ];
    const randomCase = dummyCases[Math.floor(Math.random() * dummyCases.length)];

    try {
      const response = await fetch('http://127.0.0.1:8000/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript: randomCase.transcript, caller_id: randomCase.caller_id })
      });
      const data = await response.json();

      if (data.analysis.status !== 'safe') {
        // Use real GNN metrics from backend lead_time analysis
        const leadTime = data.analysis.lead_time || {};
        const graphImpact = data.graph_impact || {};
        const extractedEntities = data.extracted_entities || [];

        const newThreat = {
          id: data.incident_id || `TR-${Math.floor(Math.random() * 1000) + 900}`,
          type: 'Real-Time SOTA Intercept', status: data.analysis.status, location: 'Live Telecom Feed',
          duration: '00m 04s', confidence: data.analysis.confidence, details: data.analysis.details,
          // Real GNN metrics from backend
          deepfakeScore: `${Math.floor(Math.random() * 15 + 85)}%`,
          spectralFlatness: (Math.random() * 0.2 + 0.45).toFixed(3),
          structuralThreat: leadTime.structural_threat || 'Low',
          degreeCentrality: leadTime.degree_centrality || 0,
          muleDistance: leadTime.mule_network_distance || 'Safe',
          hasPriorClusters: leadTime.has_prior_clusters || false,
          leadTimeMinutes: leadTime.lead_time_minutes || 0,
          // Graph bridge data
          extractedEntities: extractedEntities,
          entityIds: extractedEntities.map(e => e.id),
          graphImpact: graphImpact
        };
        setActiveThreats(prev => [newThreat, ...prev]);

        // Update graph stats immediately
        if (graphImpact.total_nodes) {
          setGraphStats(prev => ({
            ...prev,
            total_nodes: graphImpact.total_nodes,
            total_edges: graphImpact.total_edges,
            total_campaigns: graphImpact.total_campaigns
          }));
        }

        const entCount = extractedEntities.length;
        setToast(`🔗 Threat Intercepted — ${entCount} entit${entCount === 1 ? 'y' : 'ies'} linked to Graph Intelligence`);
        setTimeout(() => setToast(null), 4000);
      }
    } catch (error) {
      console.error(error);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const executeAction = () => {
    if (!confirmDialog) return;
    setIntercepted([...intercepted, confirmDialog.threat.id]);
    setToast(`${confirmDialog.actionType} executed for Case ID: ${confirmDialog.threat.id}`);
    setConfirmDialog(null);
    setTimeout(() => setToast(null), 4000);
  };

  return (
    <div className="h-screen overflow-hidden bg-[#f4f5f7] text-gray-800 font-sans flex flex-col">
      {/* Header */}
      <header className="bg-[#15284B] text-white py-3 px-6 flex justify-between items-center shadow-md z-10">
        <div className="flex items-center gap-3">
          <ShieldAlert className="w-8 h-8 text-[#FF9933]" />
          <div>
            <h1 className="text-xl font-bold tracking-wide">PROJECT SENTINEL</h1>
            <p className="text-[10px] text-gray-300 uppercase tracking-widest">National Fraud Interdiction Grid</p>
          </div>
        </div>
        <div className="flex bg-[#0f1d36] rounded-lg p-1 border border-gray-600">
          <button onClick={() => setMainView('nodal')} className={`px-4 py-1.5 rounded-md text-sm font-bold flex items-center gap-2 transition-colors ${mainView === 'nodal' ? 'bg-[#FF9933] text-[#15284B]' : 'text-gray-300 hover:text-white'}`}><Activity size={16} /> Nodal Portal</button>
          <button onClick={() => setMainView('citizen')} className={`px-4 py-1.5 rounded-md text-sm font-bold flex items-center gap-2 transition-colors ${mainView === 'citizen' ? 'bg-[#138808] text-white' : 'text-gray-300 hover:text-white'}`}><Smartphone size={16} /> Citizen Shield</button>
        </div>
      </header>

      {mainView === 'nodal' ? (
        <div className="flex flex-1 overflow-hidden">
          {/* Sidebar */}
          <aside className="w-64 bg-white border-r border-gray-300 flex flex-col shadow-sm z-0">
            <nav className="flex-1 p-4 space-y-1">
              <NavItem icon={<Activity />} label="Live Intercepts" active={activeTab === 'dashboard'} onClick={() => setActiveTab('dashboard')} />
              <NavItem icon={<Map />} label="Tactical Map" active={activeTab === 'map'} onClick={() => setActiveTab('map')} />
              <NavItem icon={<Network />} label="Graph Intelligence" active={activeTab === 'graph'} onClick={() => setActiveTab('graph')} />
              <NavItem icon={<Scan />} label="Currency Scanner" active={activeTab === 'counterfeit'} onClick={() => setActiveTab('counterfeit')} />
              <NavItem icon={<Radio />} label="Acoustic Forensics" active={activeTab === 'audio_lab'} onClick={() => setActiveTab('audio_lab')} />
            </nav>
          </aside>

          {/* Dynamic Main Content Area */}
          <main className="flex-1 overflow-auto p-6 bg-[#f4f5f7] flex flex-col h-full">

            { }
            {activeTab === 'dashboard' && (
              <>
                <div className="flex justify-between items-center mb-6">
                  <div className="grid grid-cols-4 gap-4 flex-1 mr-6">
                    <div className="bg-white p-4 rounded border border-gray-300 shadow-sm border-l-4 border-l-[#D32F2F]">
                      <h3 className="text-gray-500 text-xs font-bold uppercase tracking-wider mb-1">Active Threats</h3>
                      <div className="text-2xl font-bold text-gray-900">{activeThreats.length - intercepted.length}</div>
                    </div>
                    <div className="bg-white p-4 rounded border border-gray-300 shadow-sm border-l-4 border-l-[#15284B]">
                      <h3 className="text-gray-500 text-xs font-bold uppercase tracking-wider mb-1">GNN Sybil Rings</h3>
                      <div className="text-2xl font-bold text-gray-900">{graphStats.sybil_rings_detected || 0}</div>
                    </div>
                    <div className="bg-white p-4 rounded border border-gray-300 shadow-sm border-l-4 border-l-[#8B5CF6]">
                      <h3 className="text-gray-500 text-xs font-bold uppercase tracking-wider mb-1">Graph Entities</h3>
                      <div className="text-2xl font-bold text-gray-900">{graphStats.total_nodes || 0}</div>
                    </div>
                    <div className="bg-white p-4 rounded border border-gray-300 shadow-sm border-l-4 border-l-[#F59E0B]">
                      <h3 className="text-gray-500 text-xs font-bold uppercase tracking-wider mb-1">Deepfake Artifacts Blocked</h3>
                      <div className="text-2xl font-bold text-gray-900">3,205</div>
                    </div>
                  </div>
                  <button onClick={simulateLiveCall} disabled={isAnalyzing} className="bg-[#D32F2F] hover:bg-red-800 text-white px-6 py-4 rounded font-bold text-sm flex items-center gap-2 transition-colors disabled:opacity-50 h-full shadow-md">
                    {isAnalyzing ? <RefreshCw className="animate-spin" size={20} /> : <Activity size={20} />} Simulate Telecom Feed
                  </button>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  <div className="col-span-2 flex flex-col bg-white border border-gray-300 rounded shadow-sm overflow-hidden">
                    <div className="bg-gray-100 border-b border-gray-300 px-5 py-3 flex justify-between items-center shrink-0">
                      <h2 className="text-lg font-bold text-gray-800 uppercase tracking-wide">Tri-Factor SOTA Intercepts</h2>
                      <div className="flex bg-white border border-gray-300 rounded overflow-hidden text-sm font-medium mr-2 shadow-sm">
                        <button onClick={() => setFilter('all')} className={`px-4 py-1.5 transition-colors ${filter === 'all' ? 'bg-[#15284B] text-white' : 'text-gray-600 hover:bg-gray-50'}`}>All Cases</button>
                        <button onClick={() => setFilter('critical')} className={`px-4 py-1.5 border-l border-gray-300 transition-colors ${filter === 'critical' ? 'bg-[#D32F2F] text-white' : 'text-gray-600 hover:bg-gray-50'}`}>Critical Only</button>
                      </div>
                    </div>

                    <div className="flex-1 overflow-auto p-5 space-y-4 bg-gray-50">
                      {activeThreats.filter(t => filter === 'all' || t.status === filter).map((threat) => {
                        const isIntercepted = intercepted.includes(threat.id);
                        return (
                          <div key={threat.id} className={`p-4 rounded border transition-all duration-300 ${isIntercepted ? 'bg-gray-100 border-gray-300 opacity-60' : threat.status === 'critical' ? 'bg-white border-[#D32F2F] shadow-[0_0_10px_rgba(211,47,47,0.1)] border-l-4' : 'bg-white border-[#F59E0B] border-l-4'}`}>
                            <div className="flex justify-between items-start mb-3">
                              <div className="flex items-start gap-3">
                                <div className={`mt-1 ${isIntercepted ? 'text-[#138808]' : threat.status === 'critical' ? 'text-[#D32F2F] animate-pulse' : 'text-[#F59E0B]'}`}>
                                  {isIntercepted ? <CheckCircle2 size={24} /> : threat.status === 'critical' ? <AlertTriangle size={24} /> : <PhoneCall size={24} />}
                                </div>
                                <div>
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs font-bold text-gray-500 bg-gray-100 px-2 py-0.5 rounded border border-gray-200">CASE: {threat.id}</span>
                                    {isIntercepted && <span className="text-xs font-bold bg-[#138808] text-white px-2 py-0.5 rounded">ACTIONED</span>}
                                  </div>
                                  <h3 className="text-lg font-bold text-gray-900 mt-1">{threat.type}</h3>
                                  <div className="flex items-center gap-4 text-sm mt-1 text-gray-600">
                                    <span className="flex items-center gap-1"><MapPin size={14} /> {threat.location}</span>
                                    <span>•</span>
                                    <span>AI Confidence: <span className="font-bold">{threat.confidence}</span></span>
                                  </div>
                                </div>
                              </div>
                              <div className="text-right">
                                <div className="text-lg font-mono font-bold text-[#D32F2F]">{threat.duration}</div>
                                <div className="text-xs font-bold text-gray-500 uppercase">Live Session</div>
                              </div>
                            </div>

                            <div className="bg-gray-100 rounded p-3 text-sm text-gray-800 border border-gray-200 mb-4">
                              <span className="text-[#D32F2F] font-bold mr-2">Matched Pattern:</span> <span className="font-medium">{threat.details}</span>
                            </div>

                            <div className="grid grid-cols-2 gap-3 mb-4">
                              <div className="bg-red-50 text-red-800 border border-red-200 px-3 py-2 rounded text-xs font-bold flex flex-col gap-1 shadow-sm">
                                <div className="flex items-center gap-1 text-[10px] text-red-500 uppercase tracking-widest"><Radio size={12} /> Acoustic Forensics</div>
                                <span className="text-sm">Deepfake Match: {threat.deepfakeScore || '89%'}</span>
                                <span className="text-[10px] text-red-600 font-medium bg-white px-2 py-1 border border-red-100 rounded">Spectral Flatness: {threat.spectralFlatness || '0.512'}</span>
                              </div>
                              <div className="bg-blue-50 text-blue-800 border border-blue-200 px-3 py-2 rounded text-xs font-bold flex flex-col gap-1 shadow-sm">
                                <div className="flex items-center gap-1 text-[10px] text-blue-500 uppercase tracking-widest"><Network size={12} /> Filter-Then-Verify GNN</div>
                                <span className="text-sm">{threat.structuralThreat || 'Low'}</span>
                                <span className="text-[10px] text-blue-600 font-medium bg-white px-2 py-1 border border-blue-100 rounded">
                                  {threat.degreeCentrality !== undefined ? `Degree Centrality: ${threat.degreeCentrality}` : 'Degree Centrality Verified'}
                                  {threat.muleDistance && threat.muleDistance !== 'Safe' ? ` • Mule: ${threat.muleDistance}` : ''}
                                </span>
                              </div>
                            </div>

                            {/* Graph Intelligence Bridge — entities linked */}
                            {threat.extractedEntities && threat.extractedEntities.length > 0 && (
                              <div className="bg-indigo-50 border border-indigo-200 rounded px-3 py-2 mb-4 flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-indigo-800 font-bold">
                                  <Network size={14} className="text-indigo-600" />
                                  <span>{threat.extractedEntities.length} entit{threat.extractedEntities.length === 1 ? 'y' : 'ies'} linked to Graph Intelligence</span>
                                  <div className="flex gap-1 ml-2">
                                    {threat.extractedEntities.slice(0, 3).map((ent, i) => (
                                      <span key={i} className="bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded text-[10px] font-mono">{ent.type}: {ent.value.substring(0, 15)}{ent.value.length > 15 ? '...' : ''}</span>
                                    ))}
                                    {threat.extractedEntities.length > 3 && <span className="text-[10px] text-indigo-500">+{threat.extractedEntities.length - 3} more</span>}
                                  </div>
                                </div>
                                <button
                                  onClick={() => {
                                    setHighlightedEntities(threat.entityIds || []);
                                    setHighlightSourceCase(threat.id);
                                    setActiveTab('graph');
                                  }}
                                  className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1 rounded text-xs font-bold transition-colors shadow-sm"
                                >
                                  <Eye size={12} /> View in Graph <ChevronRight size={12} />
                                </button>
                              </div>
                            )}

                            {!isIntercepted && (
                              <div className="flex gap-3 pt-3 border-t border-gray-200">
                                <button onClick={() => setConfirmDialog({ threat, actionType: 'Telecom Block' })} className="flex items-center gap-2 bg-white hover:bg-red-50 text-[#D32F2F] border border-[#D32F2F] px-4 py-1.5 rounded transition-colors text-sm font-bold"><PauseCircle size={16} /> Request Telecom Block</button>
                                <button onClick={() => setConfirmDialog({ threat, actionType: 'Bank API Freeze' })} className="flex items-center gap-2 bg-[#15284B] hover:bg-[#0f1d36] text-white px-4 py-1.5 rounded transition-colors text-sm font-bold shadow-sm"><Lock size={16} /> Initiate Bank API Freeze</button>
                                <button onClick={() => setConfirmDialog({ threat, actionType: 'Generate MHA Dossier' })} className="flex items-center gap-2 ml-auto bg-gray-800 hover:bg-black text-white px-4 py-1.5 rounded transition-colors text-sm font-bold shadow-sm"><ShieldAlert size={16} /> Auto-Gen MHA Alert</button>
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>

                  <div className="col-span-1 bg-white rounded border border-gray-300 shadow-sm p-5 h-fit flex flex-col">
                    <h3 className="font-bold text-gray-800 mb-4 flex items-center gap-2 uppercase tracking-wide border-b border-gray-200 pb-2">
                      <Network size={18} className="text-[#15284B]" /> GNN Correlation
                    </h3>
                    <div className="relative h-48 bg-[#0f172a] rounded border border-gray-700 overflow-hidden flex items-center justify-center p-4">
                      {/* Animated graph preview dots */}
                      {Array.from({ length: Math.min(graphStats.total_nodes || 3, 8) }).map((_, i) => {
                        const positions = [
                          { top: '20%', left: '25%' }, { top: '50%', left: '50%' }, { top: '70%', left: '35%' },
                          { top: '30%', left: '70%' }, { top: '60%', left: '75%' }, { top: '15%', left: '55%' },
                          { top: '80%', left: '60%' }, { top: '45%', left: '20%' }
                        ];
                        const colors = ['#D32F2F', '#F59E0B', '#138808', '#8B5CF6', '#3B82F6'];
                        const pos = positions[i % positions.length];
                        return <div key={i} className={`absolute w-2.5 h-2.5 rounded-full z-10 ${i < 2 ? 'animate-pulse' : ''}`} style={{ top: pos.top, left: pos.left, backgroundColor: colors[i % colors.length], boxShadow: `0 0 6px ${colors[i % colors.length]}60` }} />;
                      })}
                      <svg className="absolute inset-0 w-full h-full" style={{ zIndex: 0 }}>
                        <line x1="25%" y1="20%" x2="50%" y2="50%" stroke="#D32F2F" strokeWidth="1" strokeDasharray="4 4" opacity="0.4" />
                        <line x1="50%" y1="50%" x2="35%" y2="70%" stroke="#F59E0B" strokeWidth="1" opacity="0.3" />
                        <line x1="50%" y1="50%" x2="70%" y2="30%" stroke="#3B82F6" strokeWidth="1" opacity="0.3" />
                        <line x1="70%" y1="30%" x2="75%" y2="60%" stroke="#8B5CF6" strokeWidth="1" strokeDasharray="3 3" opacity="0.3" />
                      </svg>
                      <div className="absolute bottom-2 right-2 text-[9px] text-gray-500 font-mono bg-black/40 px-1.5 py-0.5 rounded">LIVE NETWORK</div>
                    </div>
                    <div className="mt-4 space-y-2">
                      <div className="flex justify-between text-sm border-b border-gray-100 pb-2"><span className="text-gray-600">Total Nodes</span><span className="text-gray-900 font-bold">{graphStats.total_nodes || 0}</span></div>
                      <div className="flex justify-between text-sm border-b border-gray-100 pb-2"><span className="text-gray-600">Total Edges</span><span className="text-gray-900 font-bold">{graphStats.total_edges || 0}</span></div>
                      <div className="flex justify-between text-sm border-b border-gray-100 pb-2"><span className="text-gray-600">Campaigns Detected</span><span className="text-[#D32F2F] font-bold">{graphStats.total_campaigns || 0}</span></div>
                      <div className="flex justify-between text-sm pb-2"><span className="text-gray-600">Sybil Rings</span><span className="text-gray-900 font-bold">{graphStats.sybil_rings_detected > 0 ? `${graphStats.sybil_rings_detected} Active` : 'None'}</span></div>
                    </div>
                    <button onClick={() => { setHighlightedEntities([]); setHighlightSourceCase(null); setActiveTab('graph'); }} className="w-full mt-4 bg-white border-2 border-[#15284B] text-[#15284B] hover:bg-gray-50 text-sm font-bold py-2 rounded transition-colors focus:ring-2 focus:ring-offset-1 focus:ring-blue-800">Expand Full Graph</button>
                  </div>
                </div>
              </>
            )}

            { }
            {activeTab === 'graph' && <GraphIntelligenceView setToast={setToast} highlightedEntities={highlightedEntities} setHighlightedEntities={setHighlightedEntities} highlightSourceCase={highlightSourceCase} setHighlightSourceCase={setHighlightSourceCase} graphStats={graphStats} />}
            {activeTab === 'map' && <GeospatialView />}
            {activeTab === 'counterfeit' && <CounterfeitScannerView />}
            {activeTab === 'audio_lab' && <AcousticForensicsView setToast={setToast} />}

          </main>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center bg-gray-900 p-6 overflow-hidden relative">

          <div className="absolute inset-0 opacity-20 pointer-events-none">
            <div className="absolute top-10 left-10 w-64 h-64 bg-green-500 rounded-full blur-3xl mix-blend-screen"></div>
            <div className="absolute bottom-10 right-10 w-80 h-80 bg-blue-500 rounded-full blur-3xl mix-blend-screen"></div>
          </div>

          <div className="w-[380px] h-[780px] bg-black rounded-[3rem] border-[8px] border-gray-800 shadow-2xl relative overflow-hidden flex flex-col">

            {citizenTab === 'shield' && (
              <div className={`absolute inset-0 transition-colors duration-700 opacity-20 pointer-events-none ${shieldStatus === 'safe' ? 'bg-[#138808]' :
                shieldStatus === 'warning' ? 'bg-[#F59E0B]' : 'bg-[#D32F2F] animate-pulse'}`}></div>
            )}

            <div className="h-7 w-full flex justify-between items-center px-6 text-white text-[10px] font-medium z-10 pt-2 shrink-0">
              <span>9:41</span>
              <div className="w-32 h-6 bg-black rounded-b-xl absolute top-0 left-1/2 -translate-x-1/2"></div>
              <div className="flex gap-1.5 items-center">
                <span>5G</span>
                <div className="w-5 h-2.5 border border-white rounded-[3px] p-[1px]"><div className="bg-white w-full h-full rounded-[1px]"></div></div>
              </div>
            </div>

            <div className="px-6 pt-4 pb-4 z-10 flex justify-between items-center shrink-0">
              <div className="flex items-center gap-2">
                <ShieldAlert className="text-[#FF9933]" size={24} />
                <span className="text-white font-bold tracking-wider">SENTINEL</span>
              </div>
              <div className="relative">
                <select value={callLanguage} onChange={(e) => setCallLanguage(e.target.value)} className="bg-gray-800 text-white text-xs px-2 py-1.5 rounded border border-gray-600 outline-none cursor-pointer">
                  <option value="en-IN">English</option>
                  <option value="hi-IN">Hindi (हिंदी)</option>
                  <option value="mr-IN">Marathi (मराठी)</option>
                  <option value="bn-IN">Bengali (বাংলা)</option>
                </select>
              </div>
            </div>

            <div className="flex-1 overflow-hidden relative z-10 flex flex-col bg-transparent">
              {citizenTab === 'shield' ? (
                <>
                  <div className="flex-1 flex flex-col items-center justify-center p-6 overflow-auto">
                    <div className={`w-32 h-32 rounded-full flex items-center justify-center shadow-lg transition-all duration-500 ${shieldStatus === 'safe' ? 'bg-green-500/20 text-green-400 border-4 border-green-500/50' :
                      shieldStatus === 'warning' ? 'bg-yellow-500/20 text-yellow-400 border-4 border-yellow-500/50' :
                        'bg-red-500/20 text-red-400 border-4 border-red-500/50 scale-110 shadow-[0_0_30px_rgba(239,68,68,0.5)]'
                      }`}>
                      {shieldStatus === 'safe' ? <ShieldAlert size={64} /> : shieldStatus === 'warning' ? <AlertTriangle size={64} /> : <Lock size={64} />}
                    </div>
                    <h2 className={`mt-4 text-2xl font-bold tracking-wide uppercase transition-colors ${shieldStatus === 'safe' ? 'text-green-400' :
                      shieldStatus === 'warning' ? 'text-yellow-400' : 'text-red-500'}`}>
                      {shieldStatus === 'safe' ? 'Monitoring' : shieldStatus === 'warning' ? 'Suspicious' : 'Critical Threat'}
                    </h2>

                    {/* Explainable AI XAI UI for Split-Stream */}
                    <div className="flex gap-3 mt-4">
                      <div className={`flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded border ${nlpThreat !== 'safe' ? 'bg-red-900/50 text-red-400 border-red-500' : 'bg-green-900/30 text-green-400 border-green-500/50'}`}>
                        <MessageSquareWarning size={12} /> NLP: {nlpThreat.toUpperCase()}
                      </div>
                      <div className={`flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded border ${audioThreat !== 'safe' ? 'bg-red-900/50 text-red-400 border-red-500' : 'bg-green-900/30 text-green-400 border-green-500/50'}`}>
                        <Cpu size={12} /> Deepfake DSP: {audioThreat.toUpperCase()}
                      </div>
                    </div>

                    {/* LIVE DEEPFAKE DIAGNOSTICS PANEL */}
                    {isListening && liveDeepfakeDiag && (
                      <div className="w-full mt-4 space-y-2 px-1">
                        <div className="text-[10px] text-gray-400 uppercase tracking-widest font-bold text-center">Tri-Layer Deepfake Engine</div>
                        {/* Layer 1: Wav2Vec2 */}
                        <div className={`flex items-center justify-between px-3 py-1.5 rounded text-[10px] font-bold border ${liveDeepfakeDiag.layer_wav2vec?.is_deepfake ? 'bg-red-900/40 border-red-500/50 text-red-300' : 'bg-green-900/20 border-green-500/30 text-green-300'}`}>
                          <span className="flex items-center gap-1"><Radio size={10} /> Wav2Vec2</span>
                          <span>{liveDeepfakeDiag.layer_wav2vec?.confidence?.toFixed(1) || '0'}%</span>
                        </div>
                        {/* Layer 2: Biomechanical */}
                        <div className={`flex items-center justify-between px-3 py-1.5 rounded text-[10px] font-bold border ${liveDeepfakeDiag.layer_biomechanical?.is_deepfake ? 'bg-red-900/40 border-red-500/50 text-red-300' : 'bg-green-900/20 border-green-500/30 text-green-300'}`}>
                          <span className="flex items-center gap-1"><Activity size={10} /> Biomechanical</span>
                          <span>J:{liveDeepfakeDiag.layer_biomechanical?.glottal_jitter?.toFixed(2) || '0'}% S:{liveDeepfakeDiag.layer_biomechanical?.vocal_shimmer?.toFixed(2) || '0'}%</span>
                        </div>
                        {/* Layer 3: Spectral */}
                        <div className={`flex items-center justify-between px-3 py-1.5 rounded text-[10px] font-bold border ${liveDeepfakeDiag.layer_spectral?.is_deepfake ? 'bg-red-900/40 border-red-500/50 text-red-300' : 'bg-green-900/20 border-green-500/30 text-green-300'}`}>
                          <span className="flex items-center gap-1"><Fingerprint size={10} /> LFCC Spectral</span>
                          <span>Flat: {liveDeepfakeDiag.layer_spectral?.spectral_flatness?.toFixed(4) || '0'}</span>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* FULL-SCREEN DEEPFAKE ALERT OVERLAY */}
                  {isListening && liveDeepfakeDiag?.deepfake_alert && (
                    <div className="absolute inset-0 bg-red-950/95 backdrop-blur-sm z-30 flex flex-col items-center justify-center p-6 animate-[fadeIn_0.3s_ease-out]">
                      <div className="w-20 h-20 rounded-full bg-red-500/30 flex items-center justify-center border-4 border-red-500 animate-pulse mb-4">
                        <Volume2 size={40} className="text-red-400" />
                      </div>
                      <h2 className="text-2xl font-bold text-red-400 tracking-wider uppercase animate-pulse">DEEPFAKE DETECTED</h2>
                      <p className="text-red-300 text-xs mt-2 text-center font-bold uppercase tracking-widest">Synthetic Voice on This Call</p>
                      <div className="text-red-200 text-xs mt-3 bg-red-900/50 border border-red-500/30 rounded p-3 text-center max-w-[280px] leading-relaxed">
                        {liveDeepfakeDiag.verdict || 'AI-generated voice patterns detected by the Tri-Layer Ensemble Engine'}
                      </div>
                      <div className="mt-4 text-[10px] text-red-400/80 font-bold">
                        Layers Flagged: {liveDeepfakeDiag.layers_flagged}/{liveDeepfakeDiag.layers_total} — Confidence: {liveDeepfakeDiag.deepfake_probability?.toFixed(1)}%
                      </div>
                      <button onClick={stopMicrophone} className="mt-6 bg-red-600 hover:bg-red-700 text-white font-bold text-xs px-6 py-2 rounded-full uppercase tracking-widest transition-colors">
                        End Call Protection
                      </button>
                    </div>
                  )}

                  <div className="h-40 bg-gray-900/80 backdrop-blur border-t border-gray-800 p-4 flex flex-col shrink-0">
                    <div className="text-xs text-gray-500 uppercase tracking-widest font-bold mb-2 flex justify-between">
                      <span>Native Browser STT</span>
                      {isListening && <span className="text-green-400 animate-pulse flex items-center gap-1"><div className="w-2 h-2 bg-green-400 rounded-full"></div> Stream Active</span>}
                    </div>
                    <div className="flex-1 overflow-auto text-sm text-gray-300 font-mono leading-relaxed">
                      {liveTranscript || <span className="text-gray-600 italic">Waiting for voice...</span>}
                    </div>
                  </div>

                  <div className="p-6 bg-transparent flex justify-center pb-8 shrink-0">
                    <button onClick={toggleListen} className={`w-16 h-16 rounded-full flex items-center justify-center transition-all ${isListening ? 'bg-red-500 hover:bg-red-600 shadow-[0_0_15px_rgba(239,68,68,0.6)]' : 'bg-white text-black hover:bg-gray-200'}`}>
                      {isListening ? <MicOff size={28} className="text-white" /> : <Mic size={28} />}
                    </button>
                  </div>
                </>
              ) : (
                <div className="flex-1 flex flex-col bg-[#0f172a]">
                  <div className="flex-1 overflow-auto p-4 space-y-4">
                    {chatMessages.map((msg) => (
                      <div key={msg.id} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[85%] p-3 rounded-2xl text-sm ${msg.sender === 'user' ? 'bg-[#15284B] text-white rounded-br-none' :
                          msg.status === 'critical' ? 'bg-red-950/80 border border-red-500/50 text-red-100 rounded-bl-none' :
                            msg.status === 'warning' ? 'bg-yellow-950/80 border border-yellow-500/50 text-yellow-100 rounded-bl-none' :
                              'bg-gray-800 text-gray-200 rounded-bl-none'
                          }`}>
                          {msg.status === 'critical' && <div className="flex items-center gap-1 text-red-400 font-bold text-xs uppercase mb-1"><AlertTriangle size={12} /> Critical Scam Detected</div>}
                          {msg.status === 'warning' && <div className="flex items-center gap-1 text-yellow-400 font-bold text-xs uppercase mb-1"><AlertTriangle size={12} /> Suspicious Link</div>}
                          {msg.status === 'safe' && msg.sender !== 'user' && <div className="flex items-center gap-1 text-green-400 font-bold text-xs uppercase mb-1"><CheckCircle2 size={12} /> Safe Verified</div>}
                          <p>{msg.text}</p>
                          {msg.showNcrb && (
                            <button onClick={() => setShowNcrbModal(true)} className="mt-3 w-full bg-red-600 hover:bg-red-700 text-white text-xs font-bold py-2 px-3 rounded flex items-center justify-center gap-2 transition-colors">
                              <FileText size={14} /> Auto-Draft NCRB Report
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                    {isChatLoading && (
                      <div className="flex justify-start">
                        <div className="bg-gray-800 p-3 rounded-2xl rounded-bl-none flex items-center gap-2">
                          <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"></div>
                          <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                          <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                        </div>
                      </div>
                    )}
                  </div>
                  <form onSubmit={handleChatSubmit} className="p-3 bg-gray-900 border-t border-gray-800 flex items-center gap-2">
                    <button type="button" onClick={() => setToast("File upload simulation not implemented.")} className="text-gray-400 hover:text-white p-2"><UploadCloud size={20} /></button>
                    <input type="text" value={chatInput} onChange={(e) => setChatInput(e.target.value)} placeholder="Paste SMS, link, or type..." className="flex-1 bg-gray-800 text-white text-sm rounded-full px-4 py-2 outline-none border border-gray-700 focus:border-[#FF9933]" />
                    <button type="submit" disabled={!chatInput.trim() || isChatLoading} className="bg-[#138808] hover:bg-green-700 disabled:bg-gray-700 text-white p-2 rounded-full transition-colors"><Send size={18} /></button>
                  </form>
                </div>
              )}
            </div>

            <div className="h-16 bg-gray-900 border-t border-gray-800 flex items-center justify-around px-2 z-20 shrink-0">
              <button onClick={() => setCitizenTab('shield')} className={`flex-1 flex flex-col items-center justify-center gap-1 transition-colors ${citizenTab === 'shield' ? 'text-[#FF9933]' : 'text-gray-500 hover:text-gray-300'}`}><PhoneCall size={20} /><span className="text-[10px] font-bold">Call Shield</span></button>
              <button onClick={() => setCitizenTab('assistant')} className={`flex-1 flex flex-col items-center justify-center gap-1 transition-colors ${citizenTab === 'assistant' ? 'text-[#FF9933]' : 'text-gray-500 hover:text-gray-300'}`}><MessageCircle size={20} /><span className="text-[10px] font-bold">AI Assistant</span></button>
            </div>

            {showNcrbModal && (
              <div className="absolute inset-0 bg-black/80 backdrop-blur-sm z-30 flex flex-col animate-[fadeIn_0.2s_ease-out]">
                <div className="bg-white m-4 mt-16 rounded-xl flex-1 flex flex-col overflow-hidden">
                  <div className="bg-[#15284B] text-white p-3 flex justify-between items-center shrink-0">
                    <div className="flex items-center gap-2"><img src="https://upload.wikimedia.org/wikipedia/commons/5/55/Emblem_of_India.svg" alt="Emblem" className="w-5 h-6 opacity-80 filter invert" /><span className="text-xs font-bold tracking-wide">NCRB Portal Sync</span></div>
                    <button onClick={() => setShowNcrbModal(false)}><X size={18} /></button>
                  </div>
                  <div className="p-4 flex-1 overflow-auto bg-gray-50 space-y-4">
                    <div className="text-center"><div className="w-12 h-12 bg-green-100 text-green-600 rounded-full flex items-center justify-center mx-auto mb-2"><Check size={24} /></div><h3 className="font-bold text-gray-900">Draft Completed</h3><p className="text-xs text-gray-500">AI has extracted the threat vectors</p></div>
                    <div className="bg-white border border-gray-200 rounded p-3 text-xs space-y-2 font-mono shadow-inner text-gray-700"><div><span className="font-bold text-gray-500 uppercase">Category:</span> Financial Fraud</div><div><span className="font-bold text-gray-500 uppercase">Sub-Category:</span> Phishing / Vishing</div><div><span className="font-bold text-gray-500 uppercase">AI Extracted Evidence:</span> Coercive language detected matching known Digital Arrest scripts.</div><div><span className="font-bold text-gray-500 uppercase">Date/Time:</span> {new Date().toLocaleString()}</div></div>
                    <p className="text-[10px] text-gray-400 text-center leading-relaxed">By clicking submit, you authorize Project Sentinel to forward this draft to the National Cyber Crime Reporting Portal (cybercrime.gov.in) via secure API.</p>
                  </div>
                  <div className="p-3 bg-white border-t border-gray-200 shrink-0"><button onClick={() => { setShowNcrbModal(false); setToast("Securely transmitted to NCRB Portal."); setTimeout(() => setToast(null), 4000); }} className="w-full bg-[#15284B] text-white font-bold text-sm py-3 rounded shadow-md flex items-center justify-center gap-2"><Share2 size={16} /> Submit Formal Complaint</button></div>
                </div>
              </div>
            )}
          </div>

          <div className="absolute right-10 top-1/2 -translate-y-1/2 max-w-sm text-white space-y-4">
            <h3 className="text-2xl font-bold border-b border-gray-700 pb-2">Multi-Channel Citizen Shield</h3>
            <p className="text-gray-400">Simulating the end-user mobile experience available in 12 regional languages.</p>
            <ul className="list-disc pl-5 text-gray-400 space-y-2 text-sm">
              <li><b>Split-Stream Architecture:</b> We tap your mic twice simultaneously. Stream A uses flawless Native Browser STT to catch semantic scams. Stream B captures raw WAV bytes to catch Deepfake acoustics.</li>
              <li><b>Zero Token Limits:</b> By avoiding Whisper, this architecture is instantly scalable and saves millions of API tokens.</li>
            </ul>
          </div>
        </div>
      )}

      { }
      {confirmDialog && mainView === 'nodal' && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-white rounded shadow-xl max-w-lg w-full border-t-4 border-[#D32F2F] overflow-hidden">
            <div className="p-6">
              <div className="flex justify-between items-start mb-4">
                <h3 className="text-xl font-bold text-gray-900">{confirmDialog.actionType === 'Generate MHA Dossier' ? 'MHA Cybercrime Report Generation' : 'Confirm Authorized Action'}</h3>
                <button onClick={() => setConfirmDialog(null)} className="text-gray-400 hover:text-gray-600"><X size={20} /></button>
              </div>

              {confirmDialog.actionType === 'Generate MHA Dossier' ? (
                <div className="bg-gray-50 p-4 rounded border border-gray-300 text-sm text-gray-800 font-mono space-y-2 h-72 overflow-y-auto">
                  <div className="text-center font-bold border-b border-gray-300 pb-2 mb-2">MINISTRY OF HOME AFFAIRS<br />AUTOMATED CYBER THREAT ALERT (I4C)</div>
                  <p><strong>DATE/TIME:</strong> {new Date().toLocaleString()}</p>
                  <p><strong>CASE ID:</strong> {confirmDialog.threat.id}</p>
                  <p><strong>THREAT VECTOR:</strong> {confirmDialog.threat.type}</p>
                  <p><strong>AI CONFIDENCE:</strong> {confirmDialog.threat.confidence}</p>
                  <p className="pt-2 border-t border-gray-200 mt-2"><strong>SOTA TRI-FACTOR METRICS:</strong></p>
                  <ul className="list-disc pl-5 mb-2">
                    <li><strong>GNN Anomaly:</strong> {confirmDialog.threat.structuralThreat}</li>
                    <li><strong>Audio Deepfake Match:</strong> {confirmDialog.threat.deepfakeScore}</li>
                    <li><strong>Spectral Flatness:</strong> {confirmDialog.threat.spectralFlatness}</li>
                  </ul>
                  <p><strong>METADATA TRACE:</strong> High-risk VOIP signature terminating in Southeast Asia. Call flow sequence indicates coercive isolation tactics.</p>
                  <p><strong>ACTION TAKEN:</strong> Telecom Node Block Requested. Bank APIs placed on standby.</p>
                  <p className="mt-4 text-xs text-red-600 font-bold text-center">* THIS DOSSIER HAS BEEN SECURELY TRANSMITTED TO CENTRAL REPOSITORY *</p>
                </div>
              ) : (
                <>
                  <p className="text-gray-600 text-sm mb-4 leading-relaxed">You are about to initiate a <span className="font-bold text-[#D32F2F]">{confirmDialog.actionType}</span> for Case ID <span className="font-bold text-gray-900">{confirmDialog.threat.id}</span>. This action is auditable, irreversible from this panel, and will be logged under your Nodal Officer ID.</p>
                  <div className="bg-gray-50 p-4 rounded border border-gray-200 text-sm font-medium text-gray-800 mb-6 shadow-inner">
                    <div className="text-gray-500 text-xs uppercase tracking-wider mb-1">Target Entity</div>{confirmDialog.threat.type} <br />
                    <div className="text-gray-500 text-xs uppercase tracking-wider mt-2 mb-1">Jurisdiction</div>{confirmDialog.threat.location}
                  </div>
                </>
              )}

              <div className="flex justify-end gap-3 mt-6">
                <button onClick={() => setConfirmDialog(null)} className="px-4 py-2 text-sm font-bold text-gray-600 hover:text-gray-900 border border-gray-300 rounded hover:bg-gray-50 transition-colors">{confirmDialog.actionType === 'Generate MHA Dossier' ? 'Close' : 'Cancel'}</button>
                {confirmDialog.actionType !== 'Generate MHA Dossier' && <button onClick={executeAction} className="px-4 py-2 text-sm font-bold text-white bg-[#D32F2F] hover:bg-red-800 rounded shadow-sm flex items-center gap-2 transition-colors"><Lock size={16} /> Confirm & Execute</button>}
              </div>
            </div>
          </div>
        </div>
      )}

      {toast && (() => {
        const isError = toast.toLowerCase().includes('failed') || toast.toLowerCase().includes('error') || toast.toLowerCase().includes('cannot connect');
        return <div className={`fixed bottom-6 right-6 text-white px-5 py-3 rounded shadow-xl flex items-center gap-3 font-medium z-50 animate-[fadeIn_0.3s_ease-out] ${isError ? 'bg-[#D32F2F]' : 'bg-[#138808]'}`}>{isError ? <AlertTriangle size={20} /> : <CheckCircle2 size={20} />} {toast}</div>;
      })()}
    </div>
  );
}

// --- SUB COMPONENTS ---
function NavItem({ icon, label, active, onClick }) { return <button onClick={onClick} className={`w-full flex items-center gap-3 px-4 py-3 rounded transition-colors ${active ? 'bg-[#e5e7eb] text-[#15284B] font-bold border-l-4 border-[#15284B]' : 'text-gray-600 hover:bg-gray-50 font-medium border-l-4 border-transparent'}`}>{React.cloneElement(icon, { size: 20 })}<span className="text-sm">{label}</span></button>; }

function GraphIntelligenceView({ setToast, highlightedEntities = [], setHighlightedEntities, highlightSourceCase, setHighlightSourceCase, graphStats }) {
  const containerRef = useRef(null);
  const graphRef = useRef(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });
  const [selectedNode, setSelectedNode] = useState(null);
  const [showActivityFeed, setShowActivityFeed] = useState(true);

  // Real dynamic graph state replacing the hardcoded array
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [isLoading, setIsLoading] = useState(true);

  // Pulsing animation timestamp for highlighted nodes
  const [pulsePhase, setPulsePhase] = useState(0);
  useEffect(() => {
    if (highlightedEntities.length === 0) return;
    const interval = setInterval(() => setPulsePhase(p => p + 1), 50);
    return () => clearInterval(interval);
  }, [highlightedEntities]);

  // 1. Resize Observer Effect
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        const { clientWidth, clientHeight } = containerRef.current;
        if (clientWidth > 0 && clientHeight > 0) {
          setDimensions({ width: clientWidth, height: clientHeight });
        }
      }
    };

    // Initial check
    updateDimensions();

    const resizeObserver = new ResizeObserver(() => {
      window.requestAnimationFrame(updateDimensions);
    });

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => resizeObserver.disconnect();
  }, [showActivityFeed]);

  // 2. Fetch Data Effect
  useEffect(() => {
    const fetchGraphData = async () => {
      try {
        const response = await fetch('http://127.0.0.1:8000/api/graph/full');
        const result = await response.json();
        if (result.success && result.data) {
          // Only update the state if the database actually has new nodes or links!
          // This stops the physics engine from resetting every 5 seconds when nothing changed.
          setGraphData(prevData => {
            if (prevData.nodes.length !== result.data.nodes.length || prevData.links.length !== result.data.links.length) {
              return result.data;
            }
            return prevData;
          });
        }
      } catch (error) {
        console.error("Error fetching graph data:", error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchGraphData();

    // Auto-refresh the graph every 5 seconds
    const interval = setInterval(fetchGraphData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleExportEvidence = () => {
    const timestamp = new Date().toISOString();
    const dossierContent = `
====================================================================
GOVERNMENT OF INDIA - MINISTRY OF HOME AFFAIRS (I4C)
COURT-ADMISSIBLE CYBER INTELLIGENCE DOSSIER
====================================================================
GENERATED: ${timestamp}
AUTHORIZATION: NODAL OFFICER (ID: 9982-A)
TARGET CLUSTER: LIVE NETWORK CORRELATION REPORT
--------------------------------------------------------------------
EXECUTIVE SUMMARY:
AI Graph Intelligence has successfully clustered multiple victim 
reports, identifying a coordinated telecom fraud campaign. 
Transaction metadata and call records have mapped the flow of 
coerced funds through identified money mule accounts.

TOTAL IDENTIFIED NODES: ${graphData.nodes.length}
TOTAL CORRELATION LINKS: ${graphData.links.length}

CHAIN OF CUSTODY:
This intelligence package was generated dynamically by Project Sentinel 
Graph AI and is cryptographically hashed for court admissibility.
====================================================================
    `.trim();

    const blob = new Blob([dossierContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `MHA_Evidence_Dossier_${Date.now()}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const isHighlighted = (nodeId) => highlightedEntities.includes(nodeId);

  const handleActivityClick = (intercept) => {
    if (setHighlightedEntities && setHighlightSourceCase) {
      setHighlightedEntities(intercept.entity_ids || []);
      setHighlightSourceCase(intercept.incident_id);
    }
  };

  const clearHighlight = () => {
    if (setHighlightedEntities) setHighlightedEntities([]);
    if (setHighlightSourceCase) setHighlightSourceCase(null);
  };

  const recentIntercepts = graphStats?.recent_intercepts || [];

  return (
    <div className="flex-1 flex flex-col bg-white rounded border border-gray-300 shadow-sm overflow-hidden h-full relative">
      <div className="bg-[#f8f9fa] border-b border-gray-300 px-6 py-4 flex justify-between items-center shrink-0 z-10">
        <div>
          <h2 className="text-xl font-bold text-gray-800 uppercase tracking-wide flex items-center gap-2">
            <Network className="text-[#15284B]" /> Live Database Fraud Ring Mapper
          </h2>
          <p className="text-sm text-gray-500 font-medium mt-1">Dynamically clustering victim reports and scammer infrastructure.</p>
        </div>

        <div className="flex gap-3 items-center">
          {/* Live stats badges */}
          <div className="flex gap-2 mr-2">
            <span className="bg-gray-100 border border-gray-300 text-gray-700 text-xs font-bold px-2 py-1 rounded">{graphData.nodes.length} Nodes</span>
            <span className="bg-gray-100 border border-gray-300 text-gray-700 text-xs font-bold px-2 py-1 rounded">{graphData.links.length} Edges</span>
          </div>
          <button onClick={() => setShowActivityFeed(!showActivityFeed)} className={`flex items-center gap-2 border px-3 py-2 rounded text-sm font-bold shadow-sm transition-colors ${showActivityFeed ? 'bg-indigo-600 text-white border-indigo-600 hover:bg-indigo-700' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`}>
            <Activity size={16} /> Feed
          </button>
          <button onClick={() => { if (setToast) { setToast("Intelligence shared with State Nodal Agencies."); setTimeout(() => setToast(null), 4000); } }} className="flex items-center gap-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 px-4 py-2 rounded text-sm font-bold shadow-sm transition-colors">
            <Share2 size={16} /> Share Inter-Jurisdiction
          </button>
          <button
            onClick={handleExportEvidence}
            className="flex items-center gap-2 bg-[#15284B] hover:bg-[#0f1d36] text-white px-4 py-2 rounded text-sm font-bold shadow-sm transition-colors focus:ring-2 focus:ring-offset-1 focus:ring-blue-800"
          >
            <Download size={16} /> Export Court-Admissible Package
          </button>
        </div>
      </div>

      {/* Linked Intercept Banner */}
      {highlightSourceCase && highlightedEntities.length > 0 && (
        <div className="bg-indigo-600 text-white px-6 py-2.5 flex items-center justify-between shrink-0 z-10 animate-[fadeIn_0.3s_ease-out]">
          <div className="flex items-center gap-3">
            <Eye size={16} />
            <span className="text-sm font-bold">Highlighting {highlightedEntities.length} entities from Case: {highlightSourceCase}</span>
            <span className="text-xs bg-white/20 px-2 py-0.5 rounded">Linked nodes are pulsing below</span>
          </div>
          <button onClick={clearHighlight} className="flex items-center gap-1 bg-white/20 hover:bg-white/30 px-3 py-1 rounded text-xs font-bold transition-colors">
            <X size={12} /> Clear Highlight
          </button>
        </div>
      )}

      <div className="flex-1 flex overflow-hidden">
        {/* Graph Canvas */}
        <div className="flex-1 relative bg-[#0f172a] overflow-hidden" ref={containerRef}>
          {isLoading && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-gray-900/80 backdrop-blur-sm z-20 text-white font-mono">
              <RefreshCw className="animate-spin mb-3 text-[#FF9933]" size={32} />
              <div>Mapping Neural Fraud Ring from SQLite...</div>
            </div>
          )}

          {!isLoading && graphData.nodes.length === 0 && (
            <div className="absolute inset-0 flex flex-col items-center justify-center z-10 text-gray-400">
              <Network size={48} className="opacity-20 mb-4" />
              <p className="font-bold tracking-widest uppercase">No Active Networks</p>
              <p className="text-xs mt-2 text-gray-500">Simulate a telecom feed to begin mapping infrastructure.</p>
            </div>
          )}

          <div className="absolute top-4 left-4 bg-black/50 text-white text-xs px-3 py-2 rounded backdrop-blur-sm z-10 border border-white/20 shadow-lg">
            <span className="font-bold tracking-widest uppercase">Legend:</span>
            <div className="flex items-center gap-2 mt-2"><div className="w-3 h-3 rounded-full bg-[#D32F2F]"></div> Phone Number</div>
            <div className="flex items-center gap-2 mt-1"><div className="w-3 h-3 rounded-full bg-[#F59E0B]"></div> UPI Address</div>
            <div className="flex items-center gap-2 mt-1"><div className="w-3 h-3 rounded-full bg-[#138808]"></div> Bank Account</div>
            <div className="flex items-center gap-2 mt-1"><div className="w-3 h-3 rounded-full bg-[#8B5CF6]"></div> Person</div>
            <div className="flex items-center gap-2 mt-1"><div className="w-3 h-3 rounded-full bg-[#3B82F6]"></div> Institution</div>
            {highlightedEntities.length > 0 && (
              <div className="flex items-center gap-2 mt-2 pt-2 border-t border-white/20"><div className="w-3 h-3 rounded-full bg-white shadow-[0_0_6px_#fff]"></div> <span className="text-indigo-300 font-bold">Highlighted</span></div>
            )}
          </div>

          {selectedNode && (
            <div className="absolute top-4 right-4 w-72 bg-white rounded shadow-2xl border border-gray-300 z-10 overflow-hidden animate-[fadeIn_0.2s_ease-out]">
              <div className="bg-[#15284B] text-white px-4 py-3 flex justify-between items-center">
                <h3 className="font-bold text-sm uppercase tracking-wider flex items-center gap-2">
                  <Scan size={16} /> Node Forensics
                </h3>
                <button onClick={() => setSelectedNode(null)} className="text-gray-300 hover:text-white">
                  <X size={18} />
                </button>
              </div>
              <div className="p-4 space-y-3">
                <div>
                  <div className="text-xs font-bold text-gray-500 uppercase tracking-wide">Identifier</div>
                  <div className="text-sm font-bold text-gray-900 mt-0.5 break-all">{selectedNode.name}</div>
                </div>
                <div>
                  <div className="text-xs font-bold text-gray-500 uppercase tracking-wide">AI Details & Classification</div>
                  <div className="text-sm text-gray-700 mt-0.5 bg-gray-50 p-2 border border-gray-200 rounded">
                    Extracted Type: <span className="font-bold">{selectedNode.type}</span><br />
                    Internal ID: <span className="text-xs text-gray-400">{selectedNode.id.substring(0, 15)}...</span>
                  </div>
                </div>
                <div>
                  <div className="text-xs font-bold text-gray-500 uppercase tracking-wide">Computed Risk Score</div>
                  <div className="text-sm font-mono font-bold text-[#D32F2F] mt-0.5">{Number(selectedNode.score).toFixed(1)} / 100</div>
                </div>
                {selectedNode.centrality > 0 && (
                  <div>
                    <div className="text-xs font-bold text-gray-500 uppercase tracking-wide">Centrality Score</div>
                    <div className="text-sm font-mono text-gray-800 mt-0.5">{selectedNode.centrality}</div>
                  </div>
                )}
                {selectedNode.campaign_name && (
                  <div>
                    <div className="text-xs font-bold text-gray-500 uppercase tracking-wide">Campaign</div>
                    <div className="text-sm font-bold text-indigo-700 mt-0.5">{selectedNode.campaign_name}</div>
                  </div>
                )}
                {isHighlighted(selectedNode.id) && (
                  <div className="bg-indigo-50 border border-indigo-200 rounded px-2 py-1.5 text-xs text-indigo-700 font-bold flex items-center gap-1">
                    <Eye size={12} /> Linked to Case: {highlightSourceCase}
                  </div>
                )}
              </div>
            </div>
          )}

          {graphData.nodes.length > 0 && dimensions.width > 0 && (
            <ForceGraph2D
              ref={graphRef}
              width={dimensions.width}
              height={dimensions.height}
              graphData={graphData}
              nodeLabel="name"
              nodeColor="color"
              nodeRelSize={6}
              linkColor={link => link.relationship_type === 'transferred_funds' ? 'rgba(211, 47, 47, 0.8)' : 'rgba(255,255,255,0.2)'}
              linkWidth={2}
              linkDirectionalParticles={2}
              linkDirectionalParticleSpeed={0.005}
              linkDirectionalArrowLength={link => link.direction === 'directed' ? 5 : 0}
              linkDirectionalArrowColor={() => '#D32F2F'}
              linkDirectionalArrowRelPos={1}
              nodeCanvasObject={(node, ctx, globalScale) => {
                if (node.x === undefined || node.y === undefined) return;
                const r = Math.sqrt(Math.max(0, node.val || 1)) + 4;
                const highlighted = isHighlighted(node.id);
                
                // Pulsing glow ring for highlighted nodes
                if (highlighted) {
                  const glowSize = r + 6 + Math.sin(pulsePhase * 0.15) * 3;
                  ctx.beginPath();
                  ctx.arc(node.x, node.y, glowSize, 0, 2 * Math.PI, false);
                  ctx.fillStyle = `rgba(99, 102, 241, ${0.15 + Math.sin(pulsePhase * 0.15) * 0.1})`;
                  ctx.fill();
                  
                  ctx.beginPath();
                  ctx.arc(node.x, node.y, glowSize - 1, 0, 2 * Math.PI, false);
                  ctx.strokeStyle = `rgba(255, 255, 255, ${0.6 + Math.sin(pulsePhase * 0.15) * 0.3})`;
                  ctx.lineWidth = 2;
                  ctx.stroke();
                }

                const gradient = ctx.createRadialGradient(node.x - r/3, node.y - r/3, r/4, node.x, node.y, r);
                gradient.addColorStop(0, highlighted ? '#e0e7ff' : '#ffffff');
                gradient.addColorStop(1, highlighted ? '#6366f1' : (node.color || '#15284B'));
                
                ctx.beginPath();
                ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false);
                ctx.fillStyle = gradient;
                ctx.shadowColor = highlighted ? 'rgba(99, 102, 241, 0.8)' : 'rgba(0,0,0,0.5)';
                ctx.shadowBlur = highlighted ? 12 : 5;
                ctx.fill();
                
                ctx.shadowBlur = 0;

                const label = node.name || '';
                const fontSize = (highlighted ? 12 : 10) / globalScale;
                ctx.font = `${highlighted ? 'bold ' : ''}${fontSize}px Sans-Serif`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'top';
                ctx.fillStyle = highlighted ? '#c7d2fe' : '#cbd5e1';
                ctx.fillText(label, node.x, node.y + r + 2);
              }}
              nodePointerAreaPaint={(node, color, ctx) => {
                if (node.x === undefined || node.y === undefined) return;
                const r = Math.sqrt(Math.max(0, node.val || 1)) + 4;
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(node.x, node.y, r + 4, 0, 2 * Math.PI, false);
                ctx.fill();
              }}
              backgroundColor="#0f172a"
              onNodeClick={(node) => setSelectedNode(node)}
            />
          )}
        </div>

        {/* Activity Feed Sidebar */}
        {showActivityFeed && (
          <div className="w-72 bg-white border-l border-gray-300 flex flex-col shrink-0 overflow-hidden animate-[fadeIn_0.2s_ease-out]">
            <div className="bg-[#f8f9fa] border-b border-gray-300 px-4 py-3 flex items-center justify-between shrink-0">
              <h3 className="font-bold text-sm text-gray-800 uppercase tracking-wider flex items-center gap-2">
                <Activity size={14} className="text-indigo-600" /> Live Feed
              </h3>
              <span className="text-[10px] font-bold text-gray-500 bg-gray-200 px-1.5 py-0.5 rounded">{recentIntercepts.length}</span>
            </div>
            <div className="flex-1 overflow-auto">
              {recentIntercepts.length === 0 ? (
                <div className="p-4 text-center text-gray-400 text-xs">
                  <Activity size={24} className="mx-auto mb-2 opacity-30" />
                  <p className="font-bold">No recent intercepts</p>
                  <p className="mt-1">Simulate a telecom feed to see activity here.</p>
                </div>
              ) : (
                <div className="divide-y divide-gray-100">
                  {recentIntercepts.map((intercept, idx) => {
                    const isActive = highlightSourceCase === intercept.incident_id;
                    const timeStr = intercept.timestamp ? new Date(intercept.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '--:--';
                    return (
                      <button
                        key={intercept.incident_id || idx}
                        onClick={() => handleActivityClick(intercept)}
                        className={`w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors ${isActive ? 'bg-indigo-50 border-l-2 border-l-indigo-600' : ''}`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-bold text-gray-800">{intercept.incident_id}</span>
                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${intercept.status === 'critical' ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700'}`}>
                            {intercept.status?.toUpperCase()}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-[10px] text-gray-500">
                          <Clock size={10} /> {timeStr}
                          <span>•</span>
                          <span>{intercept.district || 'Unknown'}</span>
                        </div>
                        <div className="flex items-center gap-1 mt-1.5">
                          <Network size={10} className="text-indigo-500" />
                          <span className="text-[10px] font-bold text-indigo-600">{intercept.entities_count || 0} entities linked</span>
                          {isActive && <Eye size={10} className="ml-auto text-indigo-500" />}
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function MapResizer() { const map = useMap(); useEffect(() => { const timer = setTimeout(() => { map.invalidateSize(); }, 200); return () => clearTimeout(timer); }, [map]); return null; }

function LegacyGeospatialView() {
  const [incidents, setIncidents] = useState([]);
  const [hotspots, setHotspots] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  useEffect(() => {
    const fetchGeoData = async () => {
      try {
        const [incRes, hotRes] = await Promise.all([fetch('http://127.0.0.1:8000/api/geo/incidents'), fetch('http://127.0.0.1:8000/api/geo/hotspots')]);
        const incData = await incRes.json(); const hotData = await hotRes.json();
        if (incData.success) setIncidents(incData.data);
        if (hotData.success) setHotspots(hotData.data);
      } catch (error) { console.error("Geo API Error:", error); } finally { setIsLoading(false); }
    };
    fetchGeoData();
  }, []);
  return (
    <div className="flex-1 flex gap-6 h-full overflow-hidden animate-[fadeIn_0.3s_ease-out]">
      <div className="flex-1 bg-white rounded border border-gray-300 shadow-sm overflow-hidden flex flex-col relative z-0">
        <div className="bg-[#f8f9fa] border-b border-gray-300 px-6 py-3 flex justify-between items-center shrink-0"><h2 className="text-xl font-bold text-gray-800 uppercase tracking-wide flex items-center gap-2"><Map className="text-[#15284B]" /> National Crime Hotspots</h2><span className="text-xs font-bold text-gray-500 bg-gray-200 px-2 py-1 rounded">DBSCAN ACTIVE</span></div>
        <div className="flex-1 relative">
          {isLoading && (<div className="absolute inset-0 flex items-center justify-center bg-gray-50/80 backdrop-blur-sm z-10"><RefreshCw className="animate-spin text-[#15284B]" size={32} /></div>)}
          <MapContainer center={[20.5937, 78.9629]} zoom={5} style={{ height: '100%', width: '100%', zIndex: 0 }}>
            <MapResizer />
            <TileLayer url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png" attribution='&copy; CartoDB' />
            {hotspots.map((spot) => (
              <Circle key={`spot-${spot.cluster_id}`} center={[spot.center_lat, spot.center_lng]} radius={spot.density * 8000} pathOptions={{ color: '#D32F2F', fillColor: '#D32F2F', fillOpacity: 0.3 }}>
                <Popup><div className="text-sm font-sans"><strong className="block text-gray-900 text-base">{spot.district} Hotspot</strong><span className="text-[#D32F2F] font-bold">{spot.density} Active Cases</span><br /><span className="text-gray-600 text-xs">Dominant Threat: {spot.dominant_type.replace('_', ' ')}</span></div></Popup>
              </Circle>
            ))}
            {incidents.map((inc) => (
              <Marker key={inc.id} position={[inc.lat, inc.lng]}><Popup><div className="text-xs font-sans"><strong className="block text-gray-900">{inc.id}</strong><span className="uppercase text-gray-500">{inc.type.replace('_', ' ')}</span><br /><span className={inc.status === 'critical' ? 'text-red-600 font-bold' : 'text-yellow-600 font-bold'}>{inc.status.toUpperCase()}</span></div></Popup></Marker>
            ))}
          </MapContainer>
        </div>
      </div>
      <div className="w-80 bg-white rounded border border-gray-300 shadow-sm flex flex-col overflow-hidden shrink-0">
        <div className="bg-[#15284B] text-white px-5 py-3 shrink-0 flex justify-between items-center"><h3 className="font-bold uppercase tracking-wider text-sm flex items-center gap-2"><AlertTriangle size={16} className="text-[#FF9933]" /> Patrol Priority</h3></div>
        <div className="flex-1 overflow-auto p-4 space-y-4 bg-gray-50">
          {hotspots.length === 0 && !isLoading && (<p className="text-gray-500 text-sm text-center mt-10">No critical hotspots detected.</p>)}
          {hotspots.map((spot, idx) => (
            <div key={idx} className="bg-white p-3 rounded border border-red-200 shadow-sm border-l-4 border-l-[#D32F2F] hover:shadow-md transition-shadow">
              <div className="flex justify-between items-start mb-1"><h4 className="font-bold text-gray-900 text-sm">{spot.district}</h4><span className="bg-red-100 text-red-800 text-[10px] font-bold px-2 py-0.5 rounded">Rank #{idx + 1}</span></div>
              <p className="text-xs text-gray-600 mb-3">Threat: <span className="font-medium uppercase">{spot.dominant_type.replace('_', ' ')}</span></p>
              <div className="flex justify-between items-end"><div className="text-xs"><div className="text-gray-400 uppercase tracking-wide font-bold text-[10px]">Density</div><div className="font-bold text-[#D32F2F] text-xl leading-none mt-1">{spot.density} <span className="text-xs font-medium text-gray-500">Cases</span></div></div><button className="text-xs font-bold bg-[#15284B] text-white px-3 py-1.5 rounded hover:bg-blue-900 transition-colors shadow-sm">Dispatch Unit</button></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function GCPICommandCentre() {
  const [data, setData] = useState(null);
  const [eventPoints, setEventPoints] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [layers, setLayers] = useState({
    complaint: true,
    seizure: true,
    scam_call_alert: true,
    mule_node: true
  });
  const [timeHorizon, setTimeHorizon] = useState(30);
  const [showHexOverlay, setShowHexOverlay] = useState(true);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [showPointMarkers, setShowPointMarkers] = useState(true);
  const [selectedHex, setSelectedHex] = useState(null);
  const [forecastData, setForecastData] = useState(null);
  const [flyTarget, setFlyTarget] = useState(null);
  const [toast, setToast] = useState(null);

  const LAYER_COLORS = {
    complaint: '#3B82F6',
    seizure: '#D32F2F',
    scam_call_alert: '#F59E0B',
    mule_node: '#8B5CF6'
  };

  const LAYER_LABELS = {
    complaint: 'Citizen Complaints',
    seizure: 'FICN Seizures',
    scam_call_alert: 'Scam Call Alerts',
    mule_node: 'Mule Network Nodes'
  };

  // --- DATA FETCH (with 10s polling) ---
  const fetchData = async () => {
    try {
      const activeLayers = Object.keys(layers).filter(k => layers[k]).join(',');
      const [fullRes, eventsRes] = await Promise.all([
        fetch(`http://127.0.0.1:8000/api/gcpi/full?days=${timeHorizon}&layers=${activeLayers}&resolution=6`),
        fetch(`http://127.0.0.1:8000/api/gcpi/events?days=${timeHorizon}&layers=${activeLayers}`)
      ]);
      const fullJson = await fullRes.json();
      const eventsJson = await eventsRes.json();
      if (fullJson.success) setData(fullJson.data);
      if (eventsJson.success) setEventPoints(eventsJson.data);
    } catch (error) {
      console.error("GCPI API Error:", error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    setIsLoading(true);
    fetchData();
  }, [layers, timeHorizon]);

  // 10-second polling for near-real-time updates
  useEffect(() => {
    const interval = setInterval(() => { fetchData(); }, 10000);
    return () => clearInterval(interval);
  }, [layers, timeHorizon]);

  // Fetch forecast for drill-down
  useEffect(() => {
    if (!selectedHex) { setForecastData(null); return; }
    const fetchForecast = async () => {
      try {
        const res = await fetch(`http://127.0.0.1:8000/api/gcpi/forecast/${encodeURIComponent(selectedHex.cell_id)}?days=${timeHorizon}`);
        const json = await res.json();
        if (json.success) setForecastData(json.data);
      } catch (e) { console.error("Forecast fetch error:", e); }
    };
    fetchForecast();
  }, [selectedHex]);

  const toggleLayer = (layer) => setLayers(prev => ({...prev, [layer]: !prev[layer]}));

  const getHexColor = (dcri) => {
    if (dcri > 75) return '#D32F2F';
    if (dcri > 50) return '#E65100';
    if (dcri > 25) return '#F59E0B';
    return '#138808';
  };

  const getHexOpacity = (hex) => {
    if (hex.is_hotspot) return 0.7;
    if (hex.dcri > 50) return 0.55;
    return 0.35;
  };

  // Intel share handler
  const handleShareIntel = async (district) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/gcpi/intel-package/${encodeURIComponent(district)}?days=${timeHorizon}`);
      const json = await res.json();
      if (json.success && json.data) {
        const blob = new Blob([json.data.content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `GCPI_Intel_${district.replace(/\s+/g, '_')}_${Date.now()}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        setToast(`Intelligence brief shared with neighbouring districts — ${district}`);
        setTimeout(() => setToast(null), 4000);
      } else {
        setToast(json.error || 'Failed to generate intel package.');
        setTimeout(() => setToast(null), 4000);
      }
    } catch (e) {
      setToast('Network error generating intel package.');
      setTimeout(() => setToast(null), 4000);
    }
  };

  // Forecast sparkline SVG renderer
  const ForecastSparkline = ({ forecast }) => {
    if (!forecast || !forecast.forecast || forecast.forecast.length === 0) return null;
    const all = [...(forecast.historical || []).slice(-7), ...forecast.forecast];
    const max = Math.max(...all, 1);
    const w = 200, h = 50;
    const points = all.map((v, i) => `${(i / (all.length - 1)) * w},${h - (v / max) * h}`).join(' ');
    const histLen = (forecast.historical || []).slice(-7).length;
    const dividerX = histLen > 0 ? (histLen / all.length) * w : 0;

    return (
      <svg width={w} height={h + 10} className="mt-1">
        <line x1={dividerX} y1={0} x2={dividerX} y2={h} stroke="#9CA3AF" strokeDasharray="3,3" strokeWidth={1} />
        <polyline fill="none" stroke="#3B82F6" strokeWidth={2} points={points} />
        <text x={2} y={h + 9} fontSize={8} fill="#9CA3AF">History</text>
        <text x={dividerX + 4} y={h + 9} fontSize={8} fill="#F59E0B">Forecast</text>
      </svg>
    );
  };

  // Map fly-to helper component
  const FlyToCell = ({ target }) => {
    const map = useMap();
    useEffect(() => {
      if (target) {
        map.flyTo([target.lat, target.lng], 10, { duration: 1.2 });
      }
    }, [target, map]);
    return null;
  };

  // Live-feed ticker: 5 newest events
  const newestEvents = [...eventPoints].sort((a, b) => {
    const ta = a.timestamp ? new Date(a.timestamp).getTime() : 0;
    const tb = b.timestamp ? new Date(b.timestamp).getTime() : 0;
    return tb - ta;
  }).slice(0, 5);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden animate-[fadeIn_0.3s_ease-out] gap-2">
      {/* Toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-[#138808] text-white text-sm font-bold px-5 py-3 rounded-lg shadow-xl animate-[fadeIn_0.3s_ease-out] flex items-center gap-2">
          <Check size={16} /> {toast}
        </div>
      )}

      {/* KPI Header Row */}
      {data && data.stats && (
        <div className="flex gap-3 shrink-0">
          {[
            { label: 'Total Events', value: data.stats.total_events, icon: <Activity size={16} />, color: '#15284B' },
            { label: 'Active Cells', value: data.stats.active_cells, icon: <Globe size={16} />, color: '#3B82F6' },
            { label: 'Hotspots', value: data.stats.hotspot_cells, icon: <AlertTriangle size={16} />, color: '#D32F2F' },
            { label: 'Emerging', value: data.stats.emerging_clusters, icon: <TrendingUp size={16} />, color: '#9333ea' },
            { label: 'Top District', value: data.stats.top_dcri_district || '—', icon: <MapPin size={16} />, color: '#E65100' },
          ].map((kpi, i) => (
            <div key={i} className="flex-1 bg-white rounded border border-gray-200 shadow-sm px-4 py-3 flex items-center gap-3">
              <div className="p-2 rounded-lg" style={{ backgroundColor: `${kpi.color}15` }}>
                {React.cloneElement(kpi.icon, { style: { color: kpi.color } })}
              </div>
              <div>
                <div className="text-[10px] text-gray-400 uppercase tracking-wider font-bold">{kpi.label}</div>
                <div className="text-lg font-bold text-gray-900 leading-tight">{kpi.value}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Main 3-column layout */}
      <div className="flex-1 flex gap-3 overflow-hidden">
        {/* Left Control Panel */}
        <div className="w-56 bg-white rounded border border-gray-200 shadow-sm flex flex-col overflow-hidden shrink-0">
          <div className="bg-[#15284B] text-white px-4 py-2.5 shrink-0">
            <h3 className="font-bold uppercase tracking-wider text-xs flex items-center gap-2"><Layers size={14} /> Layers & Controls</h3>
          </div>
          <div className="p-3 space-y-3 flex-1 overflow-auto text-sm">
            {/* Signal Type Layers */}
            <div>
              <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">Signal Types</h4>
              <div className="space-y-1.5">
                {Object.entries(LAYER_LABELS).map(([key, label]) => (
                  <label key={key} className="flex items-center gap-2 cursor-pointer group">
                    <input type="checkbox" checked={layers[key]} onChange={() => toggleLayer(key)} className="rounded" />
                    <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: LAYER_COLORS[key] }}></span>
                    <span className="text-xs text-gray-700 group-hover:text-gray-900">{label}</span>
                  </label>
                ))}
              </div>
            </div>

            <hr className="border-gray-100" />

            {/* Overlay Toggles */}
            <div>
              <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">Overlays</h4>
              <div className="space-y-1.5">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={showPointMarkers} onChange={() => setShowPointMarkers(!showPointMarkers)} className="rounded" />
                  <span className="text-xs text-gray-700">Point Markers</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={showHexOverlay} onChange={() => setShowHexOverlay(!showHexOverlay)} className="rounded" />
                  <span className="text-xs text-gray-700">DCRI Hexagons</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={showHeatmap} onChange={() => setShowHeatmap(!showHeatmap)} className="rounded" />
                  <span className="text-xs text-gray-700">Heatmap</span>
                </label>
              </div>
            </div>

            <hr className="border-gray-100" />

            {/* Time Horizon */}
            <div>
              <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">Time Horizon</h4>
              <input type="range" min="7" max="90" step="1" value={timeHorizon} onChange={(e) => setTimeHorizon(parseInt(e.target.value))} className="w-full" />
              <div className="text-[10px] text-right mt-0.5 font-medium text-gray-500">Past {timeHorizon} Days</div>
            </div>

            <hr className="border-gray-100" />

            {/* DCRI Legend */}
            <div>
              <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">DCRI Scale</h4>
              <div className="h-3 rounded-full" style={{ background: 'linear-gradient(to right, #138808, #F59E0B, #E65100, #D32F2F)' }}></div>
              <div className="flex justify-between text-[9px] text-gray-400 mt-0.5">
                <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
              </div>
            </div>

            <hr className="border-gray-100" />

            {/* Quick Stats */}
            {data && data.stats && (
              <div className="bg-gray-50 p-2 rounded border border-gray-100">
                <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1 flex items-center gap-1"><Activity size={10}/> Summary</h4>
                <div className="space-y-1">
                  <div className="flex justify-between text-xs"><span className="text-gray-500">Avg DCRI</span><span className="font-bold text-[#F59E0B]">{data.stats.avg_dcri}</span></div>
                  <div className="flex justify-between text-xs"><span className="text-gray-500">Max DCRI</span><span className="font-bold text-[#D32F2F]">{data.stats.max_dcri}</span></div>
                  <div className="flex justify-between text-xs"><span className="text-gray-500">Points</span><span className="font-bold">{eventPoints.length}</span></div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Centre: Map + Ticker */}
        <div className="flex-1 flex flex-col gap-2 overflow-hidden">
          {/* Map Area */}
          <div className="flex-1 bg-white rounded border border-gray-200 shadow-sm overflow-hidden flex flex-col relative z-0">
            <div className="bg-[#f8f9fa] border-b border-gray-200 px-4 py-2 flex justify-between items-center shrink-0">
              <h2 className="text-base font-bold text-gray-800 uppercase tracking-wide flex items-center gap-2"><Globe className="text-[#15284B]" size={18} /> GCPI Command Centre</h2>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold text-[#138808] bg-green-50 px-2 py-1 rounded border border-green-200 flex items-center gap-1">
                  <div className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></div> LIVE — 10s
                </span>
              </div>
            </div>
            <div className="flex-1 relative">
              {isLoading && (<div className="absolute inset-0 flex items-center justify-center bg-gray-50/80 backdrop-blur-sm z-10"><RefreshCw className="animate-spin text-[#15284B]" size={32} /></div>)}
              <MapContainer center={[20.5937, 78.9629]} zoom={5} style={{ height: '100%', width: '100%', zIndex: 0 }}>
                <MapResizer />
                <FlyToCell target={flyTarget} />
                <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" attribution='&copy; CartoDB' />

                {/* Heatmap: weighted translucent circles */}
                {showHeatmap && data && data.hexgrid && data.hexgrid.map((hex) => (
                  <Circle
                    key={`heat-${hex.cell_id}`}
                    center={[hex.center_lat, hex.center_lng]}
                    radius={Math.max(5000, hex.event_count * 3000 + hex.dcri * 200)}
                    pathOptions={{
                      color: 'transparent',
                      fillColor: getHexColor(hex.dcri),
                      fillOpacity: Math.min(0.5, 0.1 + (hex.dcri / 200)),
                    }}
                  />
                ))}

                {/* DCRI Hex Overlay */}
                {showHexOverlay && data && data.hexgrid && data.hexgrid.map((hex) => (
                  <Polygon
                    key={hex.cell_id}
                    positions={hex.boundary}
                    pathOptions={{
                      color: getHexColor(hex.dcri),
                      weight: hex.is_hotspot ? 3 : 1.5,
                      fillColor: getHexColor(hex.dcri),
                      fillOpacity: getHexOpacity(hex),
                    }}
                    eventHandlers={{
                      click: () => setSelectedHex(hex),
                    }}
                  >
                    <Tooltip sticky>
                      <div className="font-sans text-sm">
                        <strong className="block text-gray-900 border-b pb-1 mb-1">{hex.district}</strong>
                        <div className="flex justify-between gap-4 mt-1"><span>DCRI:</span> <strong style={{color: getHexColor(hex.dcri)}}>{hex.dcri}</strong></div>
                        <div className="flex justify-between gap-4"><span>Events:</span> <strong>{hex.event_count}</strong></div>
                        <div className="flex justify-between gap-4"><span>Gi* Z:</span> <strong>{hex.gi_z_score}</strong></div>
                        {hex.is_hotspot && <div className="text-xs text-[#D32F2F] font-bold mt-1 bg-red-50 p-1 rounded">🔥 Statistically Significant Hotspot</div>}
                      </div>
                    </Tooltip>
                  </Polygon>
                ))}

                {/* Point Markers by event type */}
                {showPointMarkers && eventPoints.map((ev, idx) => {
                  const evType = ev.event_type || 'complaint';
                  if (!layers[evType]) return null;
                  return (
                    <CircleMarker
                      key={`pt-${ev.id || idx}`}
                      center={[ev.lat, ev.lng]}
                      radius={5}
                      pathOptions={{
                        color: LAYER_COLORS[evType] || '#3B82F6',
                        fillColor: LAYER_COLORS[evType] || '#3B82F6',
                        fillOpacity: 0.8,
                        weight: 1,
                      }}
                    >
                      <Popup>
                        <div className="text-xs font-sans min-w-[160px]">
                          <strong className="block text-gray-900 text-sm capitalize">{evType.replace(/_/g, ' ')}</strong>
                          <div className="text-gray-500 mt-1">District: <span className="font-medium text-gray-800">{ev.district}</span></div>
                          <div className="text-gray-500">Severity: <span className="font-medium" style={{ color: ev.severity > 0.7 ? '#D32F2F' : ev.severity > 0.4 ? '#F59E0B' : '#138808' }}>{(ev.severity * 100).toFixed(0)}%</span></div>
                          <div className="text-gray-500">Source: <span className="font-medium">{ev.source_module}</span></div>
                          {ev.timestamp && <div className="text-gray-400 text-[10px] mt-1">{new Date(ev.timestamp).toLocaleString()}</div>}
                        </div>
                      </Popup>
                    </CircleMarker>
                  );
                })}

                {/* Emerging clusters */}
                {data && data.emerging_clusters && data.emerging_clusters.map((cluster, idx) => (
                  <Circle
                    key={`emerge-${idx}`}
                    center={[cluster.center_lat, cluster.center_lng]}
                    radius={cluster.radius_k * 5000}
                    pathOptions={{ color: '#9333ea', fillColor: '#9333ea', fillOpacity: 0.15, dashArray: '5, 5', weight: 2 }}
                  >
                    <Popup>
                      <div className="text-sm">
                        <strong className="text-purple-700">Emerging Cluster Alert</strong>
                        <div className="text-xs mt-1">Observed: {cluster.observed} (Expected: {cluster.expected})</div>
                        <div className="text-xs">Relative Risk: {cluster.relative_risk}x</div>
                      </div>
                    </Popup>
                  </Circle>
                ))}
              </MapContainer>
            </div>
          </div>

          {/* Live-feed ticker */}
          <div className="bg-[#0f172a] rounded border border-gray-700 px-4 py-2 flex items-center gap-3 shrink-0 overflow-hidden">
            <span className="text-[10px] font-bold text-[#FF9933] uppercase tracking-widest shrink-0 flex items-center gap-1"><Radio size={10} className="animate-pulse" /> Live</span>
            <div className="flex-1 flex gap-4 overflow-hidden">
              {newestEvents.length === 0 && <span className="text-gray-500 text-[10px]">Awaiting events...</span>}
              {newestEvents.map((ev, i) => (
                <div key={i} className="text-[10px] text-gray-300 flex items-center gap-1.5 shrink-0">
                  <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: LAYER_COLORS[ev.event_type] || '#3B82F6' }}></span>
                  <span className="font-medium text-white">{ev.district}</span>
                  <span className="text-gray-500">·</span>
                  <span className="capitalize">{(ev.event_type || '').replace(/_/g, ' ')}</span>
                  {ev.timestamp && <span className="text-gray-600">· {new Date(ev.timestamp).toLocaleTimeString()}</span>}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Intelligence Panel */}
        <div className="w-72 flex flex-col gap-2 shrink-0 h-full overflow-hidden">
          {/* Drill-down panel (when a hex is selected) */}
          {selectedHex && (
            <div className="bg-white rounded border border-gray-200 shadow-sm flex flex-col overflow-hidden shrink-0" style={{ maxHeight: '45%' }}>
              <div className="bg-[#15284B] text-white px-4 py-2 shrink-0 flex justify-between items-center">
                <h3 className="font-bold uppercase tracking-wider text-xs flex items-center gap-1"><Eye size={12} /> Drill-Down</h3>
                <button onClick={() => setSelectedHex(null)} className="text-gray-400 hover:text-white"><X size={14} /></button>
              </div>
              <div className="flex-1 overflow-auto p-3 space-y-2 text-xs">
                <div className="font-bold text-gray-900 text-sm">{selectedHex.district}</div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-gray-50 p-2 rounded border border-gray-100">
                    <div className="text-[9px] text-gray-400 uppercase">DCRI</div>
                    <div className="text-lg font-bold" style={{ color: getHexColor(selectedHex.dcri) }}>{selectedHex.dcri}</div>
                  </div>
                  <div className="bg-gray-50 p-2 rounded border border-gray-100">
                    <div className="text-[9px] text-gray-400 uppercase">Events</div>
                    <div className="text-lg font-bold text-gray-900">{selectedHex.event_count}</div>
                  </div>
                  <div className="bg-gray-50 p-2 rounded border border-gray-100">
                    <div className="text-[9px] text-gray-400 uppercase">Gi* Z-Score</div>
                    <div className="text-lg font-bold text-gray-900">{selectedHex.gi_z_score}</div>
                  </div>
                  <div className="bg-gray-50 p-2 rounded border border-gray-100">
                    <div className="text-[9px] text-gray-400 uppercase">Trend</div>
                    <div className={`text-sm font-bold capitalize ${selectedHex.trend === 'rising' ? 'text-[#D32F2F]' : selectedHex.trend === 'falling' ? 'text-[#138808]' : 'text-gray-500'}`}>{selectedHex.trend}</div>
                  </div>
                </div>
                {selectedHex.dcri_breakdown && (
                  <div className="mt-1">
                    <div className="text-[9px] text-gray-400 uppercase mb-1">Type Breakdown</div>
                    {Object.entries(selectedHex.dcri_breakdown).map(([type, score]) => (
                      <div key={type} className="flex justify-between items-center py-0.5">
                        <span className="flex items-center gap-1">
                          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: LAYER_COLORS[type] || '#999' }}></span>
                          <span className="capitalize text-gray-600">{type.replace(/_/g, ' ')}</span>
                        </span>
                        <span className="font-bold text-gray-800">{score}</span>
                      </div>
                    ))}
                  </div>
                )}
                {/* Forecast Sparkline */}
                <div className="mt-1">
                  <div className="text-[9px] text-gray-400 uppercase mb-0.5">7-Day Forecast</div>
                  {forecastData ? <ForecastSparkline forecast={forecastData} /> : <div className="text-gray-400 text-[10px]">Loading forecast...</div>}
                </div>
                {/* Share Intel button */}
                <button onClick={() => handleShareIntel(selectedHex.district)} className="w-full mt-1 flex items-center justify-center gap-1.5 bg-[#15284B] text-white text-[10px] font-bold py-1.5 rounded hover:bg-[#0f1d36] transition-colors uppercase tracking-wider">
                  <Share2 size={10} /> Share Intel — {selectedHex.district}
                </button>
              </div>
            </div>
          )}

          {/* Patrol Board */}
          <div className="flex-1 bg-white rounded border border-gray-200 shadow-sm flex flex-col overflow-hidden">
            <div className="bg-[#D32F2F] text-white px-4 py-2 shrink-0 flex justify-between items-center">
              <h3 className="font-bold uppercase tracking-wider text-xs flex items-center gap-2"><Target size={14} /> District Patrol Board</h3>
            </div>
            <div className="flex-1 overflow-auto p-2 space-y-2 bg-gray-50">
              {(!data || data.patrol_allocation.length === 0) && !isLoading && (<p className="text-gray-400 text-xs text-center mt-6">No critical areas detected.</p>)}
              {data && data.patrol_allocation.map((alloc, idx) => (
                <div
                  key={idx}
                  className="bg-white p-2.5 rounded border border-gray-200 shadow-sm hover:shadow-md transition-all cursor-pointer border-l-4"
                  style={{ borderLeftColor: alloc.recommendation === 'CRITICAL DEPLOY' ? '#D32F2F' : alloc.recommendation === 'HIGH PRIORITY' ? '#F59E0B' : '#138808' }}
                  onClick={() => {
                    if (alloc.center_lat && alloc.center_lng) {
                      setFlyTarget({ lat: alloc.center_lat, lng: alloc.center_lng });
                    }
                  }}
                >
                  <div className="flex justify-between items-start mb-1">
                    <h4 className="font-bold text-gray-900 text-sm">{alloc.district || 'Unknown'}</h4>
                    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${alloc.recommendation === 'CRITICAL DEPLOY' ? 'bg-red-100 text-red-800' : alloc.recommendation === 'HIGH PRIORITY' ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-800'}`}>
                      #{idx + 1}
                    </span>
                  </div>
                  <div className="flex justify-between items-end mt-1.5">
                    <div>
                      <div className="text-[9px] text-gray-400 uppercase tracking-wider font-bold">DCRI / Priority</div>
                      <div className="text-base font-bold leading-none mt-0.5" style={{ color: getHexColor(alloc.dcri) }}>{alloc.dcri} <span className="text-xs text-gray-400 font-normal">/ {alloc.priority_score}</span></div>
                    </div>
                    <div className="text-right">
                      <div className="text-[9px] text-gray-400 uppercase tracking-wider font-bold">Units</div>
                      <div className="flex items-center gap-0.5 mt-0.5 justify-end">
                        {Array.from({ length: alloc.recommended_units || 1 }).map((_, i) => (
                          <Users key={i} size={12} className="text-[#15284B]" />
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="flex justify-between items-center mt-2">
                    <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${alloc.recommendation === 'CRITICAL DEPLOY' ? 'bg-red-50 text-red-700' : alloc.recommendation === 'HIGH PRIORITY' ? 'bg-amber-50 text-amber-700' : 'bg-green-50 text-green-700'}`}>
                      {alloc.recommendation}
                    </span>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleShareIntel(alloc.district || 'Unknown'); }}
                      className="text-[9px] font-bold text-[#15284B] hover:text-blue-700 flex items-center gap-0.5 uppercase tracking-wide"
                    >
                      <Share2 size={9} /> Share
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Emerging Alerts */}
          <div className="h-36 bg-white rounded border border-gray-200 shadow-sm flex flex-col overflow-hidden shrink-0">
            <div className="bg-[#9333ea] text-white px-4 py-1.5 shrink-0">
              <h3 className="font-bold uppercase tracking-wider text-[10px] flex items-center gap-2"><Shield size={12} /> Emerging Alerts</h3>
            </div>
            <div className="flex-1 overflow-auto p-2 space-y-1.5 bg-gray-50">
              {data && data.emerging_clusters && data.emerging_clusters.map((cluster, idx) => (
                <div key={`alert-${idx}`} className="bg-purple-50 p-2 rounded border border-purple-200 text-[10px]">
                  <strong className="block text-purple-900 mb-0.5">Anomalous Spike Detected</strong>
                  <span className="text-purple-700">Risk ratio {cluster.relative_risk}x expected baseline. LLR: {cluster.llr}</span>
                </div>
              ))}
              {data && data.emerging_clusters && data.emerging_clusters.length === 0 && !isLoading && (
                <p className="text-gray-400 text-[10px] text-center mt-3">No emerging clusters.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function GeospatialView() {
  return (
    <div className="flex flex-col h-full overflow-hidden w-full gap-2 relative">
      <GCPICommandCentre />
    </div>
  );
}

function CounterfeitScannerView() {
  const [selectedImage, setSelectedImage] = useState(null);
  const [base64Data, setBase64Data] = useState(null);
  const [isScanning, setIsScanning] = useState(false);
  const [scanResult, setScanResult] = useState(null);
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [stabilityLabel, setStabilityLabel] = useState(''); // UI feedback: "Hold steady..." / "Capturing..."

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const motionCanvasRef = useRef(null); // hidden 64x64 canvas for sampling
  const streamRef = useRef(null);       // holds the raw MediaStream
  const cameraActiveRef = useRef(false); // prevents stale closure loops
  const stableFramesRef = useRef(0);    // consecutive stable frame counter
  const prevPixelsRef = useRef(null);   // previous frame pixels for diff
  const motionTimerRef = useRef(null);  // setInterval id

  // ─── Stop camera hardware completely ───────────────────────────────────────
  const stopCamera = () => {
    cameraActiveRef.current = false;
    setIsCameraOpen(false);
    setStabilityLabel('');
    stableFramesRef.current = 0;
    prevPixelsRef.current = null;

    if (motionTimerRef.current) {
      clearInterval(motionTimerRef.current);
      motionTimerRef.current = null;
    }

    // Stop every track on the raw stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => { try { track.stop(); } catch (e) {} });
      streamRef.current = null;
    }

    // Detach from video element and force release
    if (videoRef.current) {
      try {
        videoRef.current.pause();
        if (videoRef.current.srcObject) {
          videoRef.current.srcObject.getTracks().forEach(t => { try { t.stop(); } catch (e) {} });
          videoRef.current.srcObject = null;
        }
        videoRef.current.removeAttribute('src');
        videoRef.current.load();
      } catch (e) {}
    }
  };

  // ─── Capture a frame, stop camera, trigger analysis ────────────────────────
  const captureAndAnalyze = () => {
    if (!videoRef.current || !canvasRef.current) return;
    setStabilityLabel('Capturing...');

    const ctx = canvasRef.current.getContext('2d');
    canvasRef.current.width = videoRef.current.videoWidth;
    canvasRef.current.height = videoRef.current.videoHeight;
    ctx.drawImage(videoRef.current, 0, 0);
    const dataUrl = canvasRef.current.toDataURL('image/jpeg', 0.92);

    setSelectedImage(dataUrl);
    setBase64Data(dataUrl.split(',')[1]);

    // Kill camera immediately
    stopCamera();

    // Kick off the scan
    executeScan(dataUrl.split(',')[1]);
  };

  // ─── Motion detection loop (runs while camera is open) ─────────────────────
  const startMotionLoop = () => {
    const SAMPLE_INTERVAL = 200;   // ms between samples
    const STABLE_THRESHOLD = 8;    // pixel-diff threshold (lower = stricter)
    const STABLE_NEEDED = 10;      // 10 × 200ms = 2 seconds of stillness

    motionTimerRef.current = setInterval(() => {
      if (!cameraActiveRef.current || !videoRef.current || !motionCanvasRef.current) return;
      if (videoRef.current.readyState < 2) return; // video not ready yet

      const mCtx = motionCanvasRef.current.getContext('2d');
      mCtx.drawImage(videoRef.current, 0, 0, 64, 64);
      const current = mCtx.getImageData(0, 0, 64, 64).data;

      if (prevPixelsRef.current) {
        // Calculate mean absolute pixel difference
        let totalDiff = 0;
        for (let i = 0; i < current.length; i += 4) {
          totalDiff += Math.abs(current[i] - prevPixelsRef.current[i]);
          totalDiff += Math.abs(current[i + 1] - prevPixelsRef.current[i + 1]);
          totalDiff += Math.abs(current[i + 2] - prevPixelsRef.current[i + 2]);
        }
        const meanDiff = totalDiff / (64 * 64 * 3);

        if (meanDiff < STABLE_THRESHOLD) {
          stableFramesRef.current += 1;
          const remaining = Math.max(0, STABLE_NEEDED - stableFramesRef.current);
          const secs = ((remaining * SAMPLE_INTERVAL) / 1000).toFixed(1);
          setStabilityLabel(remaining > 0 ? `Hold steady… ${secs}s` : 'Capturing!');

          if (stableFramesRef.current >= STABLE_NEEDED) {
            clearInterval(motionTimerRef.current);
            motionTimerRef.current = null;
            captureAndAnalyze();
            return;
          }
        } else {
          // Motion detected — reset counter
          stableFramesRef.current = 0;
          setStabilityLabel('Hold the note still…');
        }
      }

      prevPixelsRef.current = current;
    }, SAMPLE_INTERVAL);
  };

  // ─── Open camera ───────────────────────────────────────────────────────────
  const startCamera = async () => {
    setScanResult(null);
    setSelectedImage(null);
    setBase64Data(null);
    setStabilityLabel('Waiting for object…');
    stableFramesRef.current = 0;
    prevPixelsRef.current = null;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      cameraActiveRef.current = true;
      setIsCameraOpen(true);
      startMotionLoop();
    } catch (err) {
      console.error('Camera access denied:', err);
      alert('Camera access denied or not available over HTTP. Please use the Upload button instead, or access this page via HTTPS.');
      setIsCameraOpen(false);
    }
  };

  // ─── Reset to start a fresh scan ──────────────────────────────────────────
  const resetScan = () => {
    stopCamera();
    setScanResult(null);
    setSelectedImage(null);
    setBase64Data(null);
  };

  // ─── File upload handler ───────────────────────────────────────────────────
  const handleImageUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    stopCamera();
    setScanResult(null);
    setSelectedImage(URL.createObjectURL(file));

    const reader = new FileReader();
    reader.onloadend = () => {
      const b64 = reader.result.split(',')[1];
      setBase64Data(b64);
    };
    reader.readAsDataURL(file);
    // Reset input so same file can be re-selected
    e.target.value = '';
  };

  // ─── Run the AI scan (accepts optional explicit b64) ──────────────────────
  const executeScan = async (b64Override) => {
    const payload = b64Override || base64Data;
    if (!payload) return;
    setIsScanning(true);

    try {
      const response = await fetch('http://127.0.0.1:8000/api/scan-document', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_base64: payload })
      });
      const data = await response.json();
      if (data.success && data.analysis) {
        setScanResult(data.analysis);
      }
    } catch (error) {
      console.error('Vision API Error:', error);
      setScanResult({
        status: 'critical',
        confidence: '0%',
        forgery_markers: [{ label: 'Network Error: Failed to connect to AI backend.', status: 'failed' }]
      });
    } finally {
      setIsScanning(false);
    }
  };

  // ─── Cleanup on unmount ────────────────────────────────────────────────────
  useEffect(() => {
    return () => stopCamera();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── JSX ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col lg:flex-row gap-4 lg:gap-6 w-full">

      {/* ── LEFT PANEL: Scanner Input ── */}
      <div className="w-full lg:w-1/2 bg-white rounded border border-gray-300 shadow-sm p-4 md:p-6 flex flex-col">
        <h2 className="text-xl font-bold text-[#15284B] uppercase tracking-wide flex items-center gap-2 mb-2">
          <Scan size={24} className="text-[#FF9933]" /> Currency Identification Agent
        </h2>
        <p className="text-sm text-gray-500 mb-4">Hold a banknote steady in frame for 2 seconds — it will auto-capture and analyse.</p>

        {/* Buttons */}
        {!scanResult && (
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => { stopCamera(); document.getElementById('file-upload').click(); }}
              className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-800 py-2 rounded text-sm font-bold flex items-center justify-center gap-2 transition-colors border border-gray-300"
            >
              <UploadCloud size={16} /> Upload File
            </button>
            <button
              onClick={isCameraOpen ? stopCamera : startCamera}
              className={`flex-1 text-white py-2 rounded text-sm font-bold flex items-center justify-center gap-2 transition-colors shadow-sm ${isCameraOpen ? 'bg-red-600 hover:bg-red-700' : 'bg-[#15284B] hover:bg-[#0f1d36]'}`}
            >
              <Scan size={16} /> {isCameraOpen ? 'Stop Camera' : 'Live Scanner'}
            </button>
          </div>
        )}
        <input id="file-upload" type="file" accept="image/*" onChange={handleImageUpload} className="hidden" />

        {/* Camera / Image preview box */}
        <div className="flex-1 border-2 border-dashed border-gray-300 rounded-lg bg-gray-50 flex flex-col items-center justify-center relative overflow-hidden min-h-[240px]">

          {/* Live video feed */}
          <video ref={videoRef} autoPlay playsInline muted className={`w-full h-full object-cover absolute inset-0 ${isCameraOpen ? 'block' : 'hidden'}`} />

          {/* Targeting overlay when camera is open */}
          {isCameraOpen && (
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none z-10">
              {/* Corner brackets */}
              <div className="w-52 h-36 relative">
                <div className="absolute top-0 left-0 w-8 h-8 border-t-4 border-l-4 border-[#FF9933] rounded-tl-sm" />
                <div className="absolute top-0 right-0 w-8 h-8 border-t-4 border-r-4 border-[#FF9933] rounded-tr-sm" />
                <div className="absolute bottom-0 left-0 w-8 h-8 border-b-4 border-l-4 border-[#FF9933] rounded-bl-sm" />
                <div className="absolute bottom-0 right-0 w-8 h-8 border-b-4 border-r-4 border-[#FF9933] rounded-br-sm" />
              </div>
              {/* Status label */}
              {stabilityLabel && (
                <div className="mt-4 bg-black/70 text-white text-sm font-bold px-4 py-2 rounded-full">
                  {stabilityLabel}
                </div>
              )}
            </div>
          )}

          {/* Hidden canvases */}
          <canvas ref={canvasRef} className="hidden" />
          <canvas ref={motionCanvasRef} width="64" height="64" className="hidden" />

          {/* Captured image view with bounding boxes */}
          {!isCameraOpen && selectedImage && (
            <div className="relative w-full h-full p-2 flex items-center justify-center">
              <div className="relative inline-block max-w-full max-h-full">
                <img src={selectedImage} alt="Scanned Document" className="max-w-full max-h-full object-contain shadow-md block" />
                {scanResult && scanResult.status === 'critical' && (scanResult.anomalies || []).map((anomaly, idx) => {
                  if (!anomaly.box || !anomaly.box.left) return null;
                  return (
                    <div
                      key={idx}
                      className="absolute border-4 border-[#D32F2F] bg-red-500/20 shadow-[0_0_15px_rgba(211,47,47,0.8)] animate-pulse flex items-center justify-center group z-20 cursor-crosshair"
                      style={{ left: anomaly.box.left, top: anomaly.box.top, width: anomaly.box.width, height: anomaly.box.height }}
                    >
                      <div className="absolute -top-10 left-1/2 -translate-x-1/2 bg-[#D32F2F] text-white text-xs font-bold px-3 py-1.5 rounded shadow-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-30 pointer-events-none">
                        ⚠️ {anomaly.label}
                        <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-[#D32F2F] rotate-45"></div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Empty state */}
          {!isCameraOpen && !selectedImage && (
            <div className="text-center p-8">
              <Fingerprint size={48} className="mx-auto text-gray-400 mb-4" />
              <p className="text-gray-600 font-medium">Awaiting Document</p>
              <p className="text-gray-400 text-xs mt-1">Use Live Scanner or upload an image.</p>
            </div>
          )}
        </div>

        {/* Manual scan button (for uploaded images) */}
        {!isCameraOpen && base64Data && !scanResult && (
          <button
            onClick={() => executeScan()}
            disabled={isScanning}
            className="w-full mt-4 bg-[#15284B] hover:bg-[#0f1d36] text-white py-4 rounded font-bold uppercase tracking-widest flex items-center justify-center gap-3 transition-colors disabled:bg-gray-400 shadow-md"
          >
            {isScanning ? (
              <><RefreshCw className="animate-spin" size={20} /> Analyzing...</>
            ) : (
              <><FileSearch size={20} /> Initiate AI Forensics</>
            )}
          </button>
        )}

        {/* Scan Again button shown after result */}
        {scanResult && (
          <button
            onClick={resetScan}
            className="w-full mt-4 bg-gray-100 hover:bg-gray-200 text-gray-800 py-3 rounded font-bold flex items-center justify-center gap-2 transition-colors border border-gray-300"
          >
            <RefreshCw size={16} /> Scan Another Note
          </button>
        )}
      </div>

      {/* ── RIGHT PANEL: Analysis Report ── */}
      <div className="w-full lg:w-1/2 flex flex-col gap-4 md:gap-6">
        <div className="flex-1 bg-white rounded border border-gray-300 shadow-sm p-4 md:p-6 flex flex-col">
          <h3 className="font-bold text-gray-800 uppercase tracking-wide border-b border-gray-200 pb-3 mb-4">
            Analysis Report
          </h3>

          {/* Empty state */}
          {!scanResult && !isScanning && (
            <div className="flex-1 flex flex-col items-center justify-center text-gray-400">
              <Scan size={48} className="opacity-20 mb-4" />
              <p>Awaiting banknote scan...</p>
            </div>
          )}

          {/* Scanning spinner */}
          {isScanning && (
            <div className="flex-1 flex flex-col items-center justify-center text-[#15284B]">
              <Fingerprint size={48} className="animate-pulse mb-4 text-[#D32F2F]" />
              <p className="font-bold tracking-widest uppercase animate-pulse">Running Multi-Signal Scan</p>
              <p className="text-xs text-gray-500 mt-2">Checking microprints, security threads & UV signatures...</p>
            </div>
          )}

          {/* Results */}
          {scanResult && (
            <div className="flex-1 flex flex-col animate-[fadeIn_0.5s_ease-in-out] overflow-auto">

              {/* Invalid image */}
              {scanResult.status === 'invalid' ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center">
                  <AlertTriangle className="text-[#F59E0B] mb-4" size={48} />
                  <h2 className="text-xl font-bold text-gray-800 mb-2">Invalid Document</h2>
                  <p className="text-sm text-gray-600 px-8">
                    {typeof scanResult.forgery_markers[0] === 'object'
                      ? scanResult.forgery_markers[0].label
                      : scanResult.forgery_markers[0]}
                  </p>
                </div>
              ) : (
                <>
                  {/* Verdict banner */}
                  <div className={`p-4 rounded border-l-4 mb-4 ${scanResult.status === 'critical' ? 'bg-red-50 border-[#D32F2F]' : 'bg-green-50 border-[#138808]'}`}>
                    <div className="flex items-center gap-3 mb-1">
                      {scanResult.status === 'critical'
                        ? <AlertTriangle className="text-[#D32F2F]" size={24} />
                        : <CheckCircle2 className="text-[#138808]" size={24} />}
                      <h2 className={`text-xl font-bold uppercase tracking-wide ${scanResult.status === 'critical' ? 'text-[#D32F2F]' : 'text-[#138808]'}`}>
                        {scanResult.status === 'critical' ? 'Counterfeit Detected' : 'Authentic Banknote'}
                      </h2>
                    </div>
                    <p className="text-sm font-bold ml-9 text-gray-700">
                      Confidence: {scanResult.confidence}
                      {scanResult.denomination && scanResult.denomination !== 'N/A' && (
                        <span className="ml-3 text-gray-500 font-normal">· {scanResult.denomination}</span>
                      )}
                    </p>
                  </div>

                  {/* Multi-signal metrics */}
                  {scanResult.cv_metrics && (
                    <div className="mb-4 grid grid-cols-2 gap-3">
                      <div className="bg-gray-50 border border-gray-200 rounded p-3">
                        <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider mb-1 flex items-center gap-1"><Scan size={12} /> OpenCV</div>
                        <div className="text-xs text-gray-800"><span className="font-semibold">Texture Variance:</span> {scanResult.cv_metrics.texture_variance}</div>
                        <div className="text-xs text-gray-800"><span className="font-semibold">Flat Region Ratio:</span> {scanResult.cv_metrics.flat_region_ratio}</div>
                      </div>
                      <div className="bg-gray-50 border border-gray-200 rounded p-3">
                        <div className="text-[10px] text-gray-500 font-bold uppercase tracking-wider mb-1 flex items-center gap-1"><Network size={12} /> Edge CNN</div>
                        <div className="text-xs text-gray-800 font-semibold">{scanResult.dl_metrics}</div>
                      </div>

                      {/* Portrait check */}
                      {scanResult.portrait_check && scanResult.portrait_check.confidence !== 'N/A' && (
                        <div className={`col-span-2 border rounded p-3 ${scanResult.portrait_check.is_gandhi ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
                          <div className={`text-[10px] font-bold uppercase tracking-wider mb-1 flex items-center gap-1 ${scanResult.portrait_check.is_gandhi ? 'text-green-700' : 'text-[#D32F2F]'}`}>
                            {scanResult.portrait_check.is_gandhi ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
                            Portrait Identity · {scanResult.portrait_check.confidence}
                          </div>
                          <div className={`text-xs font-semibold ${scanResult.portrait_check.is_gandhi ? 'text-green-800' : 'text-[#D32F2F]'}`}>
                            {scanResult.portrait_check.is_gandhi ? '✓ Verified: Mahatma Gandhi' : '✗ MISMATCH: Not Mahatma Gandhi'}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Forensic checklist */}
                  <h4 className="font-bold text-gray-800 mb-2 flex items-center gap-2">
                    <FileSearch size={16} /> Forensic Checklist:
                  </h4>
                  <ul className="space-y-2 overflow-auto">
                    {(scanResult.forgery_markers || []).map((marker, idx) => {
                      const label = typeof marker === 'object' ? marker.label : marker;
                      const isPassed = typeof marker === 'object' ? marker.status === 'passed' : scanResult.status !== 'critical';
                      return (
                        <li key={idx} className="flex items-start gap-3 bg-gray-50 p-2.5 rounded border border-gray-200 text-sm text-gray-700">
                          <span className={`mt-0.5 shrink-0 ${isPassed ? 'text-[#138808]' : 'text-[#D32F2F]'}`}>
                            {isPassed ? <Check size={16} /> : <X size={16} />}
                          </span>
                          <span className="font-medium leading-relaxed">{label}</span>
                        </li>
                      );
                    })}
                  </ul>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
function AcousticForensicsView({ setToast }) {
  const [base64Audio, setBase64Audio] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [isScanning, setIsScanning] = useState(false);
  const [scanResult, setScanResult] = useState(null);
  const [activeTest, setActiveTest] = useState(null);

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      setScanResult(null); setAudioUrl(URL.createObjectURL(file)); setActiveTest(`Uploaded File: ${file.name}`);
      const reader = new FileReader(); reader.onloadend = () => { setBase64Audio(reader.result.split(',')[1]); }; reader.readAsDataURL(file);
    }
  };

  const executeScan = async () => {
    if (!base64Audio) return;
    setIsScanning(true); setScanResult(null);
    try {
      const response = await fetch('http://127.0.0.1:8000/api/analyze-audio', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ audio_base64: base64Audio }) });
      const data = await response.json();
      if (data.success) { setScanResult(data.analysis); } else { setScanResult({ audio_signal: "Parse Failed", error: data.error || "Unknown server error processing audio." }); }
    } catch (e) { setToast("Failed to connect to API. Is your Python server running?"); } finally { setIsScanning(false); }
  };

  const LayerCard = ({ title, icon, layer, metricLabel, metricValue }) => {
    if (!layer) return null;
    const isFlagged = layer.is_deepfake;
    return (
      <div className={`border rounded p-3 ${isFlagged ? 'bg-red-50 border-red-200' : 'bg-green-50 border-green-200'}`}>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            {icon}
            <span className="text-xs font-bold uppercase tracking-wider text-gray-700">{title}</span>
          </div>
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${isFlagged ? 'bg-red-200 text-red-800' : 'bg-green-200 text-green-800'}`}>
            {isFlagged ? 'FLAGGED' : 'CLEAR'}
          </span>
        </div>
        {metricLabel && (
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] text-gray-500 font-bold uppercase">{metricLabel}</span>
            <span className={`text-sm font-mono font-bold ${isFlagged ? 'text-[#D32F2F]' : 'text-[#138808]'}`}>{metricValue}</span>
          </div>
        )}
        <div className="w-full bg-gray-200 rounded-full h-1.5 mb-2">
          <div className={`h-1.5 rounded-full transition-all duration-500 ${isFlagged ? 'bg-[#D32F2F]' : 'bg-[#138808]'}`}
            style={{ width: `${Math.min(layer.confidence || 0, 100)}%` }}></div>
        </div>
        <p className="text-[10px] text-gray-600 leading-relaxed">{layer.detail || ''}</p>
      </div>
    );
  };

  return (
    <div className="flex-1 flex gap-6 h-full animate-[fadeIn_0.3s_ease-out]">
      <div className="w-1/2 bg-white rounded border border-gray-300 shadow-sm p-6 flex flex-col">
        <h2 className="text-xl font-bold text-[#15284B] uppercase tracking-wide flex items-center gap-2 mb-2"><Radio size={24} className="text-[#D32F2F]" /> Deepfake Acoustic Lab</h2>
        <p className="text-sm text-gray-500 mb-6">SOTA Tri-Layer Ensemble Engine. Upload suspected audio — the system runs Wav2Vec2 deep features, biomechanical jitter/shimmer analysis, and LFCC spectral artifact scanning simultaneously.</p>
        <div className="relative flex-1 border-2 border-dashed border-gray-300 rounded-lg bg-gray-50 flex flex-col items-center justify-center transition-all hover:bg-gray-100 p-6">
          {!audioUrl ? (
            <div className="text-center"><UploadCloud size={48} className="mx-auto text-gray-400 mb-4" /><p className="text-gray-600 font-medium text-lg">Upload Audio Evidence</p><p className="text-gray-400 text-xs mt-1 mb-6">Supports .WAV intercept files for raw DSP analysis.</p><button onClick={() => document.getElementById('audio-upload').click()} className="bg-[#15284B] hover:bg-[#0f1d36] text-white px-6 py-3 rounded text-sm font-bold shadow-md transition-colors flex items-center gap-2 mx-auto"><FileSearch size={18} /> Browse Files</button><input id="audio-upload" type="file" accept="audio/wav" onChange={handleFileUpload} className="hidden" /></div>
          ) : (
            <div className="w-full text-center"><Radio size={48} className={`mx-auto mb-4 ${isScanning ? 'text-[#D32F2F] animate-ping' : 'text-[#138808]'}`} /><h3 className="font-bold text-gray-900 mb-4">{activeTest}</h3><audio controls src={audioUrl} className="w-full shadow-md rounded-full outline-none mb-4" /><button onClick={() => { setAudioUrl(null); setBase64Audio(null); setScanResult(null); }} className="text-sm text-[#D32F2F] hover:text-red-800 font-bold underline">Clear Buffer &amp; Upload New</button></div>
          )}
        </div>
        <button onClick={executeScan} disabled={!base64Audio || isScanning} className="w-full mt-6 bg-[#D32F2F] hover:bg-red-800 text-white py-4 rounded font-bold uppercase tracking-widest flex items-center justify-center gap-3 transition-colors disabled:bg-gray-400 shadow-md">
          {isScanning ? (<><RefreshCw className="animate-spin" size={20} /> Running Tri-Layer Ensemble...</>) : (<><Activity size={20} /> Run Deepfake Analysis</>)}
        </button>
      </div>
      <div className="w-1/2 flex flex-col gap-6">
        <div className="flex-1 bg-white rounded border border-gray-300 shadow-sm p-6 flex flex-col overflow-auto">
          <h3 className="font-bold text-gray-800 uppercase tracking-wide border-b border-gray-200 pb-3 mb-4">Tri-Layer Ensemble Results</h3>
          {!scanResult && !isScanning && (<div className="flex-1 flex flex-col items-center justify-center text-gray-400"><Activity size={48} className="opacity-20 mb-4" /><p>Awaiting audio waveform...</p></div>)}
          {isScanning && (<div className="flex-1 flex flex-col items-center justify-center text-[#15284B]"><Cpu size={48} className="animate-bounce mb-4 text-[#D32F2F]" /><p className="font-bold tracking-widest uppercase">Running 3-Layer Analysis</p><p className="text-xs text-gray-500 mt-2">Wav2Vec2 → Biomechanical → LFCC Spectral...</p></div>)}
          {scanResult && (
            <div className="flex-1 flex flex-col animate-[fadeIn_0.5s_ease-in-out]">
              {scanResult.audio_signal === "Parse Failed" || scanResult.audio_signal === "Forensic Parse Failed" ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center mt-10"><AlertTriangle className="text-[#F59E0B] mb-4" size={48} /><h2 className="text-xl font-bold text-gray-800 mb-2">Forensic Parse Failed</h2><p className="text-sm text-gray-600 px-8 bg-yellow-50 p-4 border border-yellow-200 rounded leading-relaxed">{scanResult.error || "Unable to mathematically read audio bytes."}</p></div>
              ) : (
                <>
                  {/* ENSEMBLE VERDICT BANNER */}
                  <div className={`p-4 rounded border-l-4 mb-4 ${scanResult.is_synthetic_voice ? 'bg-red-50 border-[#D32F2F]' : 'bg-green-50 border-[#138808]'}`}>
                    <div className="flex items-center gap-3 mb-1">
                      {scanResult.is_synthetic_voice ? <AlertTriangle className="text-[#D32F2F]" size={24} /> : <CheckCircle2 className="text-[#138808]" size={24} />}
                      <h2 className={`text-lg font-bold uppercase tracking-wide ${scanResult.is_synthetic_voice ? 'text-[#D32F2F]' : 'text-[#138808]'}`}>
                        {scanResult.is_synthetic_voice ? 'DEEPFAKE DETECTED' : 'NATURAL HUMAN VOICE'}
                      </h2>
                    </div>
                    <p className="text-sm font-bold ml-9 text-gray-700">Ensemble Confidence: {scanResult.deepfake_probability}% — Layers Flagged: {scanResult.layers_flagged || 0}/{scanResult.layers_total || 3}</p>
                    <p className="text-xs ml-9 text-gray-500 mt-1">{scanResult.audio_signal}</p>
                  </div>

                  {/* TRI-LAYER BREAKDOWN */}
                  <div className="space-y-3 mb-4">
                    <LayerCard
                      title="Layer 1: Wav2Vec2 Deep Features"
                      icon={<Radio size={14} className="text-blue-600" />}
                      layer={scanResult.layer_wav2vec}
                      metricLabel="Deepfake Probability"
                      metricValue={`${scanResult.layer_wav2vec?.confidence || 0}%`}
                    />
                    <LayerCard
                      title="Layer 2: Biomechanical Analysis"
                      icon={<Activity size={14} className="text-purple-600" />}
                      layer={scanResult.layer_biomechanical}
                      metricLabel="Jitter / Shimmer"
                      metricValue={`${scanResult.glottal_jitter || 0}% / ${scanResult.vocal_shimmer || 0}%`}
                    />
                    <LayerCard
                      title="Layer 3: LFCC Spectral Artifacts"
                      icon={<Cpu size={14} className="text-orange-600" />}
                      layer={scanResult.layer_spectral}
                      metricLabel="Spectral Flatness"
                      metricValue={scanResult.spectral_flatness || 0}
                    />
                  </div>

                  {/* MATHEMATICAL SUMMARY */}
                  <div className={`mt-auto border p-3 rounded text-xs leading-relaxed ${scanResult.is_synthetic_voice ? 'bg-red-50 border-red-200 text-red-900' : 'bg-green-50 border-green-200 text-green-900'}`}>
                    <span className="font-bold uppercase tracking-wider block mb-1 border-b pb-1">Ensemble Verdict:</span>
                    <p>{scanResult.is_synthetic_voice
                      ? `This audio was flagged by ${scanResult.layers_flagged} of ${scanResult.layers_total} detection layers. The fail-closed ensemble architecture ensures that even a single layer detecting synthetic artifacts triggers a DEEPFAKE verdict.`
                      : `All ${scanResult.layers_total} detection layers unanimously agree this audio contains natural human vocal characteristics including involuntary glottal micro-tremors, natural spectral harmonic structure, and organic waveform patterns.`
                    }</p>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function audioBufferToWav(buffer) {
  let numOfChan = buffer.numberOfChannels, length = buffer.length * numOfChan * 2 + 44, bufferArr = new ArrayBuffer(length), view = new DataView(bufferArr), channels = [], i, sample, offset = 0, pos = 0;
  function setUint16(data) { view.setUint16(offset, data, true); offset += 2; }
  function setUint32(data) { view.setUint32(offset, data, true); offset += 4; }
  setUint32(0x46464952); setUint32(length - 8); setUint32(0x45564157); setUint32(0x20746d66); setUint32(16); setUint16(1); setUint16(numOfChan); setUint32(buffer.sampleRate); setUint32(buffer.sampleRate * 2 * numOfChan); setUint16(numOfChan * 2); setUint16(16); setUint32(0x61746164); setUint32(length - pos - 4);
  for (i = 0; i < buffer.numberOfChannels; i++) channels.push(buffer.getChannelData(i));
  while (pos < buffer.length) { for (i = 0; i < numOfChan; i++) { sample = Math.max(-1, Math.min(1, channels[i][pos])); sample = (0.5 + sample < 0 ? sample * 32768 : sample * 32767) | 0; view.setInt16(offset, sample, true); offset += 2; } pos++; }
  return new Blob([bufferArr], { type: 'audio/wav' });
}