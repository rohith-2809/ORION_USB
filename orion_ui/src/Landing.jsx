import { useEffect, useRef, useState } from 'react';
import { FiClock, FiMenu, FiMessageSquare, FiShield, FiTrash2, FiX } from 'react-icons/fi';
import { IoSend } from 'react-icons/io5';
import { io } from 'socket.io-client';


const OrionAI = () => {
  // Core states
  const [bootStep, setBootStep] = useState('blue');
  const [bootComplete, setBootComplete] = useState(false);
  const [aiState, setAiState] = useState('idle');
  const [godMode, setGodMode] = useState(false);
  const [clickPulse, setClickPulse] = useState(false);
  const [sendPulse, setSendPulse] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [isWakeDetected, setIsWakeDetected] = useState(false);

  // Chat Mode State
  const [isChatMode, setIsChatMode] = useState(false);
  const [chatHistory, setChatHistory] = useState([]);
  const chatEndRef = useRef(null);

  // Document Generation State
  const [isGenerating, setIsGenerating] = useState(false);
  const [genTimer, setGenTimer] = useState(0);

  useEffect(() => {
    if (chatEndRef.current) {
        chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatHistory, isGenerating]);

  // Handle Muting Voice when Chat Mode engages
  useEffect(() => {
    if (!bootComplete) return;
    try {
        fetch('http://localhost:3000/api/voice_status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ active: !isChatMode })
        });
    } catch (e) {
        console.warn("Could not sync voice status with Orion.");
    }
  }, [isChatMode, bootComplete]);

  // Monitoring States
  const [protectiveAction, setProtectiveAction] = useState(false);
  const [systemHealth, setSystemHealth] = useState({
    cpu: 23, memory: 32, temp: 42, threats: 0, lastAction: "System Secure"
  });

  // Sidebar State
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  // Greeting State
  const greetings = [
    "ORION ONLINE.",
    "AWAITING DIRECTIVE.",
    "COGNITIVE CORE ACTIVE.",
    "SYSTEM READY."
  ];
  const [greetingIndex, setGreetingIndex] = useState(0);

  // Rotate greetings
  useEffect(() => {
    if (!bootComplete) return;
    const interval = setInterval(() => {
        setGreetingIndex(prev => (prev + 1) % greetings.length);
    }, 4000);
    return () => clearInterval(interval);
  }, [bootComplete]);

  // Boot sequence
  useEffect(() => {
    const timer1 = setTimeout(() => setBootStep('orange'), 700);
    const timer2 = setTimeout(() => setBootStep('green'), 1400);
    const timer3 = setTimeout(() => {
      setBootComplete(true);
      setAiState('idle');
      // Set the greeting text
      setLastResponse("ORION IS AT YOUR SERVICE, SIR.");
    }, 2100);
    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
    };
  }, []);

  // Voice & Scan State
  const [isListening, setIsListening] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [scanResult, setScanResult] = useState(null);

  // Clean State
  const [isCleaning, setIsCleaning] = useState(false);
  const [cleanResult, setCleanResult] = useState(null);

  // Integrity State
  const [isCheckingIntegrity, setIsCheckingIntegrity] = useState(false);
  const [integrityResult, setIntegrityResult] = useState(null);

  // Monitor Real System Health
  useEffect(() => {
    if (!bootComplete) return;
    const interval = setInterval(async () => {
        try {
            const res = await fetch('http://localhost:3000/api/status');
            const data = await res.json();
            if (data.cpu !== undefined) {
                setSystemHealth(prev => ({
                    ...prev,
                    cpu: Math.round(data.cpu),
                    memory: Math.round(data.memory),
                    threats: data.threats,
                    lastAction: data.threats > 0 ? "Threat Detected" : "System Secure"
                }));
            }
        } catch (e) {
            // Ignore connection errors, keep polling
        }
    }, 2000);
    return () => clearInterval(interval);
  }, [bootComplete]);

  // [NEW] Socket.IO Voice Sync
  useEffect(() => {
      const socket = io('http://localhost:3000');

      socket.on('connect', () => {
          console.log("Connected to Orion Brain via Socket.IO");
      });

      socket.on('voice_status', (data) => {
          console.log("Voice Event:", data);
          if (data.source === 'orion' && data.state === 'speaking') {
              setAiState('speaking');
          } else if (data.source === 'user' && data.state === 'speaking') {
              setAiState(prev => {
                  if (prev === 'idle') {
                      setIsWakeDetected(true);
                      setTimeout(() => setIsWakeDetected(false), 800);
                  }
                  return 'listening';
              });
          } else if (data.state === 'processing') {
              setAiState('processing');
          } else {
              setAiState('idle');
          }
      });

      return () => socket.close();
  }, []);

  // Voice Functionality
  const speak = (text) => {
      const utterance = new SpeechSynthesisUtterance(text);
      // Select a futuristic voice if available
      const voices = window.speechSynthesis.getVoices();
      const preferred = voices.find(v => v.name.includes("Google US English") || v.name.includes("Microsoft Zira"));
      if (preferred) utterance.voice = preferred;
      window.speechSynthesis.speak(utterance);
  };

  const startListening = () => {
      if (!('webkitSpeechRecognition' in window)) {
          alert("Browser does not support Speech Recognition.");
          return;
      }

      const recognition = new window.webkitSpeechRecognition();
      recognition.continuous = false;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
          setIsListening(true);
          setAiState('listening');
      };

      recognition.onend = () => {
          setIsListening(false);
          // if not speaking, go idle
          if (aiState === 'listening') setAiState('idle');
      };

      recognition.onresult = (event) => {
          const text = event.results[0][0].transcript;
          setInputValue(text);
          // Auto-send
          handleSend(null, text);
      };

      recognition.start();
  };

  const triggerScan = async () => {
      setIsScanning(true);
      setScanResult(null);

      try {
          const res = await fetch('http://localhost:3000/api/scan', { method: 'POST' });
          const data = await res.json();
          setTimeout(() => {
              // Mock Result for Demo purposes, as backend is async
              const mockRes = { issues_found: 1, details: ["suspicious_file.exe (Mock)"] };
              setScanResult(mockRes);
              setIsScanning(false);
              speak(`Scan initiated. Background process started.`);
          }, 1500);
      } catch (e) {
          setIsScanning(false);
          setScanResult({ error: "Scan failed to connect." });
      }
  };

  const triggerClean = async () => {
      setIsCleaning(true);
      setCleanResult(null);

      try {
          const res = await fetch('http://localhost:3000/api/clean', { method: 'POST' });
          const data = await res.json();
          setTimeout(() => {
              // Mock Result for Demo
              const mockRes = { status: "Background Clean Started", files_removed: "Calculating...", space_reclaimed_mb: "0.0" };
              setCleanResult(mockRes);
              setIsCleaning(false);
              speak(`Cleanup initiated in background.`);
          }, 1500);
      } catch (e) {
          setIsCleaning(false);
          setCleanResult({ error: "Cleanup failed to connect." });
      }
  };

  const triggerIntegrity = async () => {
      setIsCheckingIntegrity(true);
      setIntegrityResult(null);

      try {
          const res = await fetch('http://localhost:3000/api/integrity', { method: 'POST' });
          const data = await res.json();
          setTimeout(() => {
              setIntegrityResult({ status: "Running", message: "SFC Check running in background. This may take 20+ minutes." });
              setIsCheckingIntegrity(false);
              speak("Integrity check initiated. This will determine system health.");
          }, 2000);
      } catch (e) {
          setIsCheckingIntegrity(false);
          setIntegrityResult({ error: "Integrity Check failed to connect." });
      }
  };






  // Generation Timer
  useEffect(() => {
    let interval;
    if (isGenerating) {
        interval = setInterval(() => setGenTimer(t => t + 0.1), 100);
    } else {
        setGenTimer(0);
    }
    return () => clearInterval(interval);
  }, [isGenerating]);

  // Compute ring color
  const getRingColor = () => {
    if (!bootComplete) {
      switch (bootStep) {
        case 'blue': return '#3b82f6';
        case 'orange': return '#f97316';
        case 'green': return '#22c55e';
        default: return '#22c55e';
      }
    }
    if (godMode) return '#f97316';
    if (systemHealth.threats > 0) return '#ffaa00'; // Orange for Threats
    if (isGenerating) return '#22c55e'; // Green for Generation
    if (isChatMode) return '#4AF3FF'; // Soft Blue for Chat Mode
    switch (aiState) {
      case 'speaking':
      case 'listening':
      case 'processing':
        return '#4AF3FF';
      default:
        return '#22c55e';
    }
  };
  const ringColor = getRingColor();

  // Animation params
  const getRingAnimation = () => {
    if (!bootComplete) return { rotate: false, dashFlow: false, dashArray: 'none' };
    if (godMode) return { rotate: 'fast', dashFlow: false, dashArray: '4, 16' };
    if (isGenerating) return { rotate: 'fast', dashFlow: true, dashArray: '10, 10' }; // Fast Green Rotation
    switch (aiState) {
      case 'speaking':
        // Wave-like flow: Multiple overlapping segments mimicking a fluid wave
        return { rotate: 'slow', dashFlow: true, dashArray: '80, 20, 40, 60, 20, 100' };
      case 'processing':
        // Thinking / Generating state: fast flowing dashed ring
        return { rotate: 'fast', dashFlow: true, dashArray: '10, 10' };
      case 'listening':
        // User sync: simple rotation
        return { rotate: 'slow', dashFlow: false, dashArray: '2, 10' };
      default:
        return { rotate: false, dashFlow: false, dashArray: 'none' };
    }
  };
  const ringAnim = getRingAnimation();

  const clickCountRef = useRef(0);
  const clickTimerRef = useRef(null);

  // Handlers
  const handleOrbClick = () => {
    setClickPulse(true);
    setTimeout(() => setClickPulse(false), 250);

    clickCountRef.current += 1;

    if (clickTimerRef.current) {
      clearTimeout(clickTimerRef.current);
    }

    clickTimerRef.current = setTimeout(() => {
      const clicks = clickCountRef.current;
      clickCountRef.current = 0; // reset

      if (clicks === 1) {
        // Normal Mode (un-click)
        setGodMode(false);
        setIsChatMode(false);
        setLastResponse("SYSTEM NORMALIZED.");
      } else if (clicks === 2) {
        // God Mode Toggle
        setGodMode(prev => {
             const nextState = !prev;
             if (nextState) {
                 setLastResponse("GOD MODE ACTIVATED.");
             } else {
                 setLastResponse("GOD MODE DEACTIVATED.");
             }
             return nextState;
         });
      } else if (clicks >= 3) {
        // Chat Mode Toggle
        setGodMode(false);
        setIsChatMode(prev => !prev);
        setLastResponse("CHAT MODE TOGGLED.");
      }
    }, 350); // wait 350ms to accumulate clicks
  };

  const [lastResponse, setLastResponse] = useState('');

  const handleSend = async (e, overrideText = null) => {
    if (e) e.preventDefault();
    const textToSend = overrideText || inputValue;

    if (!textToSend.trim()) return;

    // Detect Generation Intent
    const isGenIntent = textToSend.match(/create|generate|make|build/i) && textToSend.match(/ppt|word|doc|presentation|report/i);
    const isConfirm = textToSend.match(/yes|confirm|proceed|okay/i);

    // Trigger Green Orb if intent matches
    if (isGenIntent || isConfirm) {
        setIsGenerating(true);
    }

    setChatHistory(prev => [...prev, { role: 'user', content: textToSend }]);
    setInputValue('');
    setAiState('speaking');
    setIsChatMode(true);
    setSendPulse(true);
    setTimeout(() => setSendPulse(false), 300);

    try {
      const res = await fetch('http://localhost:3000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: textToSend, god_mode: godMode, chat_mode: isChatMode })
      });

      const data = await res.json();
      console.log("Orion Response:", data);

      if (data && data.content) {
        setLastResponse(data.content);
        setChatHistory(prev => [...prev, { role: 'orion', content: data.content }]);
        speak(data.content); // TTS Result
        setTimeout(() => setAiState('idle'), Math.min(5000, data.content.length * 50 + 1000));
      } else {
        setAiState('idle');
      }

    } catch (error) {
      console.error("Connection Error:", error);
      setLastResponse("Error: Could not connect to Orion System.");
      setAiState('idle');
    } finally {
        setIsGenerating(false);
    }
  };

  const handleFocus = () => {
    if (bootComplete && !godMode) setAiState('listening');
  };

  const handleBlur = () => {
    if (bootComplete && aiState === 'listening' && !godMode) setAiState('idle');
  };

  // ... rest of the component

  const toggleSidebar = () => {
    setIsSidebarOpen(prev => !prev);
  };

  return (
    <div className="min-h-screen bg-[#050505] flex flex-col items-center justify-center overflow-hidden relative">

      {/* --- AMBIENT GRID BACKGROUND --- */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.03]"
        style={{
            backgroundImage: 'radial-gradient(circle at 1px 1px, #ffffff 1px, transparent 0)',
            backgroundSize: '40px 40px'
        }}
      />

      {/* --- PROTECTIVE FLASH OVERLAY --- */}
      {protectiveAction && (
          <div className="absolute inset-0 z-0 bg-red-500/10 animate-pulse pointer-events-none transition-opacity duration-500" />
      )}

      {/* --- SIDEBAR (History) --- */}
      <div
        className={`fixed top-0 left-0 h-full w-80 bg-[#0a0a0a] border-r border-gray-800 z-50 transform transition-transform duration-500 ease-in-out ${
          isSidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="p-8 pt-24 relative h-full">
            {/* BACK BUTTON IN SIDEBAR */}
            <button
                onClick={toggleSidebar}
                className="absolute top-6 left-6 p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-full transition-all"
            >
                <FiX size={20} />
            </button>

            <h2 className="text-gray-400 text-xs tracking-[0.2em] uppercase mb-6 flex items-center gap-2 mt-4">
                <FiClock /> Session History
            </h2>
            <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                    <div key={i} className="group p-4 rounded-xl bg-white/5 hover:bg-white/10 transition cursor-pointer border border-transparent hover:border-gray-700">
                        <div className="flex items-center justify-between mb-2">
                            <span className="text-blue-400 text-xs">0{i}:42 PM</span>
                            <FiMessageSquare className="text-gray-600 group-hover:text-gray-400" size={12} />
                        </div>
                        <p className="text-gray-300 text-sm truncate">System analysis complete. Optimization recommended.</p>
                    </div>
                ))}
            </div>

            <div className="absolute bottom-8 left-8 right-8">
                 <div className="text-xs text-gray-700 text-center tracking-widest">ORION OS v2.1</div>
            </div>
        </div>
      </div>

      {/* --- MAIN CONTAINER (FULL SCREEN) --- */}
      <div
        className={`relative flex-1 w-full flex flex-col items-center justify-center transition-all duration-500 ease-in-out z-30 ${
            isSidebarOpen ? 'pl-80' : ''
        }`}
      >

        {/* HAMBURGER (Fixed Top Left) */}
        {!isSidebarOpen && (
            <div
                className="absolute top-8 left-8 text-gray-400 hover:text-white transition-colors cursor-pointer z-50 p-2 rounded-full hover:bg-white/5 mix-blend-difference"
                onClick={toggleSidebar}
            >
            <FiMenu size={24} />
            </div>
        )}

        {/* Content Centered */}
        <div className={`flex flex-col items-center justify-center w-full transition-all duration-500 ${isSidebarOpen ? 'scale-95' : 'scale-100'} ${isChatMode ? 'h-full justify-start pt-6 pb-28' : ''}`}>

          {/* ORB */}
          <div
            className={`relative cursor-pointer transition-all duration-700 ease-in-out ${
              isChatMode
                ? 'w-20 h-20 md:w-24 md:h-24 flex-shrink-0 z-20 mb-6 mt-4'
                : 'w-64 h-64 md:w-80 md:h-80 mb-10'
            } ${clickPulse && !isChatMode ? 'scale-102' : 'scale-100'}`}
            style={{
                filter: isChatMode ? 'drop-shadow(0 0 30px rgba(59,130,246,0.4))' : ''
            }}
            onClick={handleOrbClick}
          >
            {/* Ambient Layer */}
            <div
              className="absolute inset-0 rounded-full opacity-10 blur-xl"
              style={{
                background: `radial-gradient(circle at 30% 30%, ${ringColor}, transparent 70%)`,
                transition: 'background 0.5s ease',
              }}
            />

             {/* Wake Word Ripple */}
            {isWakeDetected && (
              <div className="absolute inset-0 rounded-full animate-wake-ripple pointer-events-none" />
            )}

             {/* Protective Ring Ping */}
            {protectiveAction && (
              <div className="absolute inset-0 rounded-full border-2 border-red-500/60 animate-ping pointer-events-none" />
            )}

            {/* Inner Core (Static) */}
            <div
              className="absolute inset-0 rounded-full bg-black flex items-center justify-center z-10"
              style={{
                background: 'radial-gradient(circle at 30% 30%, #2a2a2a, #000000)',
                boxShadow: isChatMode
                    ? 'inset 0 0 20px rgba(59,130,246,0.2), 0 0 0 1px rgba(59,130,246,0.2)'
                    : 'inset 0 2px 8px rgba(0,0,0,0.8), 0 0 0 1px rgba(255,255,255,0.03)',
                transition: 'box-shadow 0.5s ease'
              }}
            >
              <div className="absolute top-0 left-1/4 w-1/2 h-1/3 bg-white opacity-5 rounded-full blur-md" />
              <span
                className={`tracking-[0.2em] font-light z-20 select-none transition-all duration-500 ${
                  isChatMode
                    ? 'text-sm md:text-base text-blue-400 opacity-80'
                    : 'text-3xl md:text-4xl text-white'
                }`}
                style={{
                  textShadow: `0 0 12px ${ringColor}`,
                  transition: 'text-shadow 0.3s ease',
                }}
              >
                O R I O N
              </span>
            </div>

            {/* Outer Ring (Animated) */}
            <div
              className={`absolute inset-0 rounded-full pointer-events-none ${
                ringAnim.rotate === 'slow' ? 'animate-rotate-slow' : ''
              } ${ringAnim.rotate === 'fast' ? 'animate-rotate-fast' : ''} ${
                aiState === 'listening' ? 'animate-listen-pulse' : ''
              }`}
              style={{
                filter: `drop-shadow(0 0 12px ${ringColor})${sendPulse ? ' brightness(1.5)' : ''}`,
                transition: 'filter 0.2s ease, drop-shadow 0.3s ease',
              }}
            >
              <svg viewBox="0 0 100 100" className="w-full h-full" style={{ overflow: 'visible' }}>
                <circle
                  cx="50" cy="50" r="46"
                  fill="none"
                  stroke={ringColor}
                  strokeWidth="2"
                  strokeDasharray={ringAnim.dashArray}
                  strokeDashoffset={ringAnim.dashFlow ? 0 : undefined}
                  strokeLinecap="round"
                  style={{
                    transition: 'stroke 0.3s ease',
                    animation: ringAnim.dashFlow ? 'dash-flow 3s linear infinite' : 'none',
                  }}
                />
              </svg>
            </div>

            {/* Idle Breath */}
            {bootComplete && aiState === 'idle' && !godMode && !isGenerating && (
              <div
                className="absolute inset-0 rounded-full opacity-0 animate-breath"
                style={{
                  background: `radial-gradient(circle at 50% 50%, ${ringColor}20, transparent 70%)`,
                  filter: 'blur(20px)',
                }}
              />
            )}
          </div>

          {/* EXTERNAL GENERATION TIMER */}
          {isGenerating && !isChatMode && (
            <div
              className="mt-6 font-mono text-sm tracking-[0.2em] animate-pulse"
              style={{ color: ringColor, textShadow: `0 0 8px ${ringColor}` }}
            >
                GENERATING RESPONSE... {genTimer.toFixed(1)}s
            </div>
          )}

          {/* CHAT LOG / PROMPTS */}
          {isChatMode ? (
            <div className="flex-1 w-full max-w-4xl flex flex-col gap-6 px-4 overflow-y-auto mb-6 scrollbar-hide z-20 pb-36">
              {chatHistory.length === 0 && !isGenerating && (
                <div className="flex-1 flex items-center justify-center text-[#4AF3FF] opacity-50 font-light tracking-widest text-sm">
                  CHAT MODE ENGAGED. AWAITING COMMAND.
                </div>
              )}
              {chatHistory.map((msg, idx) => (
                <div key={idx} className={`flex w-full ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] rounded-2xl px-5 py-3.5 font-light text-[15px] leading-relaxed relative ${
                    msg.role === 'user'
                      ? 'bg-white/5 text-white border border-white/10 rounded-br-sm'
                      : 'bg-[#4AF3FF]/5 text-white border border-[#4AF3FF]/20 rounded-bl-sm shadow-[0_0_15px_rgba(74,243,255,0.05)]'
                  }`}>
                     {msg.role === 'orion' && (
                         <div className="absolute -left-3 -top-3 w-6 h-6 rounded-full bg-black border border-[#4AF3FF]/30 flex items-center justify-center shadow-[0_0_10px_rgba(74,243,255,0.2)]">
                            <div className="w-1.5 h-1.5 rounded-full bg-[#4AF3FF]"></div>
                         </div>
                     )}
                     <span className="whitespace-pre-wrap">{msg.content}</span>
                  </div>
                </div>
              ))}
              {isGenerating && (
                 <div className="flex w-full justify-start">
                    <div className="bg-[#4AF3FF]/5 text-[#4AF3FF] border border-[#4AF3FF]/20 rounded-2xl rounded-bl-sm px-6 py-4 font-mono text-xs animate-pulse tracking-widest flex items-center gap-3">
                        <div className="w-2 h-2 rounded-full bg-[#4AF3FF]"></div>
                        GENERATING RESPONSE...
                    </div>
                 </div>
              )}
              <div ref={chatEndRef} />
            </div>
          ) : (
            <div className="mb-8 text-center h-28 flex flex-col items-center justify-between">
              {/* Rotating Prompts */}
              <p
                key={greetingIndex}
                className="text-lg md:text-xl font-light tracking-[0.1em] animate-fade transition-colors duration-500 text-gray-300"
                style={{ textShadow: '0 0 10px rgba(255,255,255,0.1)' }}
              >
                {greetings[greetingIndex]}
              </p>
            </div>
          )}

          {/* Chat Form Section */}
          <div className={`transition-all duration-700 w-full flex justify-center z-50 ${
            isChatMode ? 'fixed bottom-8 px-4 max-w-4xl' : ''
          }`}>
          <form
            onSubmit={handleSend}
            className={`flex items-center gap-3 transition-all duration-700 ease-in-out ${
                isChatMode ? 'w-full shadow-[0_0_30px_rgba(74,243,255,0.15)] rounded-full bg-[#050505] border border-gray-800' : 'w-full max-w-md'
            }`}
          >
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onFocus={handleFocus}
              onBlur={handleBlur}
              placeholder={isChatMode ? "Conversation active..." : "Command..."}
              className={`flex-1 bg-white/5 border rounded-full px-6 py-3 text-white placeholder-gray-600 focus:outline-none focus:bg-white/10 transition-all duration-300 ${
                  isChatMode ? 'border-[#4AF3FF]/50 focus:border-[#4AF3FF]' : 'border-gray-700/50 focus:border-[#4AF3FF]/50'
              }`}
              style={{
                borderColor: godMode ? '#f97316' : systemHealth.threats > 0 ? '#ffaa00' : isChatMode ? '#4AF3FF' : '',
              }}
            />
            <button
              type="submit"
              className={`w-12 h-12 rounded-full bg-white/5 border flex items-center justify-center hover:bg-white/10 transition-all duration-300 ${
                  isChatMode ? 'border-[#4AF3FF]/50 text-[#4AF3FF] shadow-[0_0_15px_rgba(74,243,255,0.5)]' : 'border-gray-700/50'
              }`}
              style={{
                color: godMode ? '#f97316' : systemHealth.threats > 0 ? '#ffaa00' : '#4AF3FF',
                borderColor: godMode ? '#f97316' : systemHealth.threats > 0 ? '#ffaa00' : '#4AF3FF',
              }}
            >
              {isGenerating ? <div className="text-[10px] font-mono animate-pulse">{genTimer.toFixed(0)}s</div> : <IoSend size={18} />}
            </button>
          </form>
          </div>

        </div>
      </div>


        {/* SCAN MODAL */}
        {scanResult && (
            <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm" onClick={() => setScanResult(null)}>
                <div className="bg-gray-900 border border-red-500/50 p-8 rounded-xl max-w-md w-full relative" onClick={e => e.stopPropagation()}>
                    <h3 className="text-red-400 text-xl font-bold tracking-widest mb-4 flex items-center gap-2">
                        <FiClock className="animate-pulse"/> SYSTEM SCAN REPORT
                    </h3>
                    <div className="space-y-2 text-gray-300 mb-6 font-mono text-sm">
                        <p>Issues Found: <span className="text-white font-bold">{scanResult.issues_found}</span></p>
                        <ul className="list-disc pl-5 space-y-1 text-xs text-gray-500">
                             {scanResult.details?.map((d, i) => <li key={i}>{d}</li>)}
                        </ul>
                    </div>
                    <button
                        onClick={() => setScanResult(null)}
                        className="w-full py-2 bg-red-500/20 hover:bg-red-500/40 text-red-300 border border-red-500/50 rounded uppercase text-xs tracking-widest transition"
                    >
                        Acknowledge
                    </button>
                </div>
            </div>
        )}

        {/* CLEAN RESULT MODAL */}
        {cleanResult && (
            <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm" onClick={() => setCleanResult(null)}>
                <div className="bg-gray-900 border border-orange-500/50 p-8 rounded-xl max-w-md w-full relative" onClick={e => e.stopPropagation()}>
                    <h3 className="text-orange-400 text-xl font-bold tracking-widest mb-4 flex items-center gap-2">
                        <FiTrash2 className="animate-pulse"/> CLEANUP REPORT
                    </h3>
                    <div className="space-y-2 text-gray-300 mb-6 font-mono text-sm">
                        <p>Status: <span className="text-white font-bold">{cleanResult.status}</span></p>
                        <p>Files Removed: <span className="text-white font-bold">{cleanResult.files_removed}</span></p>
                        <p>Space Reclaimed: <span className="text-white font-bold">{cleanResult.space_reclaimed_mb} MB</span></p>
                    </div>
                    <button
                        onClick={() => setCleanResult(null)}
                        className="w-full py-2 bg-orange-500/20 hover:bg-orange-500/40 text-orange-300 border border-orange-500/50 rounded uppercase text-xs tracking-widest transition"
                    >
                        Close
                    </button>
                </div>
            </div>
        )}

        {/* INTEGRITY RESULT MODAL */}
        {integrityResult && (
            <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm" onClick={() => setIntegrityResult(null)}>
                <div className="bg-gray-900 border border-cyan-500/50 p-8 rounded-xl max-w-md w-full relative" onClick={e => e.stopPropagation()}>
                    <h3 className="text-cyan-400 text-xl font-bold tracking-widest mb-4 flex items-center gap-2">
                        <FiShield className="animate-pulse"/> INTEGRITY CHECK
                    </h3>
                    <div className="space-y-2 text-gray-300 mb-6 font-mono text-sm">
                        <p>Status: <span className="text-white font-bold">{integrityResult.status || "Error"}</span></p>
                        <p className="text-xs text-cyan-200">{integrityResult.message || integrityResult.error}</p>
                    </div>
                    <button
                        onClick={() => setIntegrityResult(null)}
                        className="w-full py-2 bg-cyan-500/20 hover:bg-cyan-500/40 text-cyan-300 border border-cyan-500/50 rounded uppercase text-xs tracking-widest transition"
                    >
                        Acknowledge
                    </button>
                </div>
            </div>
        )}

        {/* CONTROLS */}
        <div className="absolute top-8 right-8 z-40 flex gap-4">
             <button
                onClick={triggerScan} disabled={isScanning || isCleaning}
                className={`p-3 rounded-full border transition-all ${isScanning ? 'bg-red-500/20 border-red-500 animate-pulse' : 'bg-black/50 border-gray-700 hover:border-red-500 text-gray-400 hover:text-red-400'}`}
             >
                 {isScanning ? <span className="text-xs font-bold px-2">SCANNING...</span> : <FiClock size={20} title="Deep Scan"/>}
             </button>
             <button
                onClick={triggerClean} disabled={isCleaning || isScanning || isCheckingIntegrity}
                className={`p-3 rounded-full border transition-all ${isCleaning ? 'bg-orange-500/20 border-orange-500 animate-pulse' : 'bg-black/50 border-gray-700 hover:border-orange-500 text-gray-400 hover:text-orange-400'}`}
             >
                 {isCleaning ? <span className="text-xs font-bold px-2">CLEANING...</span> : <FiTrash2 size={20} title="System Clean"/>}
             </button>
             <button
                onClick={triggerIntegrity} disabled={isScanning || isCleaning || isCheckingIntegrity}
                className={`p-3 rounded-full border transition-all ${isCheckingIntegrity ? 'bg-cyan-500/20 border-cyan-500 animate-pulse' : 'bg-black/50 border-gray-700 hover:border-cyan-500 text-gray-400 hover:text-cyan-400'}`}
             >
                 {isCheckingIntegrity ? <span className="text-xs font-bold px-2">CHECKING...</span> : <FiShield size={20} title="Integrity Check"/>}
             </button>
             <button
                onClick={startListening}
                className={`p-3 rounded-full border transition-all ${isListening ? 'bg-blue-500/20 border-blue-500 animate-pulse text-blue-400' : 'bg-black/50 border-gray-700 hover:border-blue-500 text-gray-400 hover:text-blue-400'}`}
             >
                 <FiMessageSquare size={20} title="Voice Command"/>
             </button>
        </div>


        {/* FOOTER */}
        <div className="absolute bottom-6 w-full text-center z-20 pointer-events-none">
            <p className="text-[10px] text-gray-600 uppercase tracking-[0.4em] opacity-60">
                ORION - A cognitive intelligence
            </p>
        </div>


    </div>
  );
};

export default OrionAI;
