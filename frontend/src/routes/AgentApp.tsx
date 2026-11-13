import React, { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../lib/api";

// ---------------------------------------------------------------------------
// Type Definitions
// ---------------------------------------------------------------------------

export interface AgentProfile {
  id: string;
  fpo_id: string;
  name: string;
  phone: string;
}

export interface CollectionPoint {
  id: string;
  fpo_id: string;
  name: string;
  district_code: string;
}

export interface FarmerListing {
  id: string;
  farmer_name: string;
  farmer_phone: string;
  village: string;
  qty_qtl: number;
  ask_price: number;
}

export interface Cluster {
  id: string;
  collection_point_id: string;
  collection_point_name: string;
  crop_code: string;
  status: "OPEN" | "VERIFIED" | "BIDDING" | "ACCEPTED" | "CLOSED" | string;
  total_qtl: number;
  listing_count: number;
  min_ask: number;
  wavg_ask: number;
  grade: string | null;
  version: number;
}

export interface ClusterDetail extends Cluster {
  listings: FarmerListing[];
}

export interface VerificationHistoryItem {
  id: string;
  cluster_id: string;
  crop_code: string;
  total_qtl: number;
  grade: string;
  moisture_pct: number | null;
  notes: string | null;
  photo_url: string;
  verified_at: string;
}

export interface OfflineVerification {
  cluster_id: string;
  grade: string;
  moisture_pct: string;
  notes: string;
  photo_base64: string;
  photo_name: string;
  photo_type: string;
  queued_at: string;
  lat?: string;
  lon?: string;
}

// ---------------------------------------------------------------------------
// Main Component: AgentApp (FPO Field Agent PWA)
// ---------------------------------------------------------------------------

export default function AgentApp(): React.ReactElement {
  // --- Auth State ---
  const [token, setToken] = useState<string | null>(() => {
    try {
      return localStorage.getItem("token");
    } catch {
      return null;
    }
  });
  const [agent, setAgent] = useState<AgentProfile | null>(() => {
    try {
      const stored = localStorage.getItem("agent_profile");
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });

  // Login form state
  const [phoneInput, setPhoneInput] = useState<string>("+919800000101");
  const [pinInput, setPinInput] = useState<string>("1234");
  const [loginLoading, setLoginLoading] = useState<boolean>(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  // --- App Navigation ---
  const [activeTab, setActiveTab] = useState<"clusters" | "inspect" | "history">("clusters");

  // --- Network & PWA State ---
  const [isOnline, setIsOnline] = useState<boolean>(navigator.onLine);
  const [installPrompt, setInstallPrompt] = useState<any>(null);

  // --- Data States ---
  const [collectionPoints, setCollectionPoints] = useState<CollectionPoint[]>([]);
  const [selectedCpId, setSelectedCpId] = useState<string>("all");
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [clustersLoading, setClustersLoading] = useState<boolean>(false);
  const [clustersError, setClustersError] = useState<string | null>(null);

  // Inspection & Verification State
  const [activeClusterId, setActiveClusterId] = useState<string | null>(null);
  const [clusterDetail, setClusterDetail] = useState<ClusterDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);

  // Verification Form Inputs
  const [selectedGrade, setSelectedGrade] = useState<"A" | "B" | "C">("A");
  const [moistureInput, setMoistureInput] = useState<string>("");
  const [notesInput, setNotesInput] = useState<string>("");
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [submittingVerification, setSubmittingVerification] = useState<boolean>(false);
  const [verificationFeedback, setVerificationFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // Verification History
  const [historyItems, setHistoryItems] = useState<VerificationHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState<boolean>(false);

  // Offline Queue
  const [offlineQueue, setOfflineQueue] = useState<OfflineVerification[]>(() => {
    try {
      const q = localStorage.getItem("offline_verifications");
      return q ? JSON.parse(q) : [];
    } catch {
      return [];
    }
  });

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // ---------------------------------------------------------------------------
  // Connectivity & PWA Listeners
  // ---------------------------------------------------------------------------

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    const handleBeforeInstall = (e: any) => {
      e.preventDefault();
      setInstallPrompt(e);
    };
    window.addEventListener("beforeinstallprompt", handleBeforeInstall);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("beforeinstallprompt", handleBeforeInstall);
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Authentication Handlers
  // ---------------------------------------------------------------------------

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError(null);
    setLoginLoading(true);

    try {
      const res = await api.post("/api/agent/login", {
        phone: phoneInput.trim(),
        pin: pinInput.trim(),
      });

      if (res && res.token) {
        setToken(res.token);
        setAgent(res.agent);
        try {
          localStorage.setItem("token", res.token);
          localStorage.setItem("agent_profile", JSON.stringify(res.agent));
        } catch {}
      }
    } catch (err: any) {
      setLoginError(err?.body?.message || err?.message || "Login failed. Check phone and PIN.");
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = () => {
    setToken(null);
    setAgent(null);
    try {
      localStorage.removeItem("token");
      localStorage.removeItem("agent_profile");
    } catch {}
    setActiveTab("clusters");
  };

  // ---------------------------------------------------------------------------
  // Load Collection Points & Clusters
  // ---------------------------------------------------------------------------

  const loadCollectionPoints = useCallback(async () => {
    if (!token) return;
    try {
      const cps: CollectionPoint[] = await api.get("/api/agent/collection-points");
      setCollectionPoints(cps || []);
    } catch (err) {
      console.warn("Could not load collection points:", err);
    }
  }, [token]);

  const loadClusters = useCallback(async () => {
    if (!token) return;
    setClustersLoading(true);
    setClustersError(null);
    try {
      const path =
        selectedCpId !== "all"
          ? `/api/agent/clusters?collection_point_id=${selectedCpId}`
          : "/api/agent/clusters";
      const data: Cluster[] = await api.get(path);
      setClusters(data || []);
    } catch (err: any) {
      setClustersError(err?.body?.message || err?.message || "Failed to load clusters");
    } finally {
      setClustersLoading(false);
    }
  }, [token, selectedCpId]);

  const loadHistory = useCallback(async () => {
    if (!token) return;
    setHistoryLoading(true);
    try {
      const data: VerificationHistoryItem[] = await api.get("/api/agent/verifications");
      setHistoryItems(data || []);
    } catch (err) {
      console.warn("Failed to load verification history:", err);
    } finally {
      setHistoryLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (token) {
      loadCollectionPoints();
      loadClusters();
      loadHistory();
    }
  }, [token, loadCollectionPoints, loadClusters, loadHistory]);

  // Load cluster detail when selected
  useEffect(() => {
    if (!activeClusterId || !token) {
      setClusterDetail(null);
      return;
    }
    let isCancelled = false;
    setDetailLoading(true);

    api
      .get(`/api/agent/clusters/${activeClusterId}`)
      .then((data: ClusterDetail) => {
        if (!isCancelled) {
          setClusterDetail(data);
        }
      })
      .catch((err: any) => {
        if (!isCancelled) {
          console.error("Failed to load cluster detail:", err);
        }
      })
      .finally(() => {
        if (!isCancelled) setDetailLoading(false);
      });

    return () => {
      isCancelled = true;
    };
  }, [activeClusterId, token]);

  // ---------------------------------------------------------------------------
  // Photo Capture & Preview
  // ---------------------------------------------------------------------------

  const handlePhotoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate size (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
      setVerificationFeedback({
        type: "error",
        message: "Photo size exceeds 10MB. Please take another photo.",
      });
      return;
    }

    setPhotoFile(file);
    const reader = new FileReader();
    reader.onload = (event) => {
      setPhotoPreview(event.target?.result as string);
    };
    reader.readAsDataURL(file);
    setVerificationFeedback(null);
  };

  const handleClearPhoto = () => {
    setPhotoFile(null);
    setPhotoPreview(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // ---------------------------------------------------------------------------
  // Verification Submission (Online / Offline)
  // ---------------------------------------------------------------------------

  const handleSubmitVerification = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeClusterId) return;

    if (!photoFile && !photoPreview) {
      setVerificationFeedback({
        type: "error",
        message: "A live photograph of the produce is required for verification.",
      });
      return;
    }

    setSubmittingVerification(true);
    setVerificationFeedback(null);

    // If offline, store in offline queue
    if (!navigator.onLine) {
      const offlineItem: OfflineVerification = {
        cluster_id: activeClusterId,
        grade: selectedGrade,
        moisture_pct: moistureInput,
        notes: notesInput,
        photo_base64: photoPreview || "",
        photo_name: photoFile?.name || "produce.jpg",
        photo_type: photoFile?.type || "image/jpeg",
        queued_at: new Date().toISOString(),
      };
      const newQueue = [...offlineQueue, offlineItem];
      setOfflineQueue(newQueue);
      try {
        localStorage.setItem("offline_verifications", JSON.stringify(newQueue));
      } catch {}

      setVerificationFeedback({
        type: "success",
        message: "Saved offline. Verification will sync automatically once connection returns.",
      });
      setSubmittingVerification(false);
      return;
    }

    // Online submission
    try {
      // Capture live GPS location if available
      let lat: number | null = null;
      let lon: number | null = null;
      if (navigator.geolocation) {
        try {
          const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, {
              enableHighAccuracy: true,
              timeout: 10000,
            });
          });
          lat = pos.coords.latitude;
          lon = pos.coords.longitude;
        } catch (geoErr) {
          console.warn("Could not capture GPS location:", geoErr);
        }
      }

      const formData = new FormData();
      formData.append("grade", selectedGrade);
      if (moistureInput.trim()) {
        formData.append("moisture_pct", moistureInput.trim());
      }
      if (notesInput.trim()) {
        formData.append("notes", notesInput.trim());
      }
      if (lat !== null && lon !== null) {
        formData.append("lat", lat.toFixed(6));
        formData.append("lon", lon.toFixed(6));
      }
      if (photoFile) {
        formData.append("photo", photoFile, photoFile.name);
      }

      const res = await api.postForm(`/api/agent/clusters/${activeClusterId}/verify`, formData);

      setVerificationFeedback({
        type: "success",
        message: `Cluster verified successfully as Grade ${res.grade}! Status updated to VERIFIED.`,
      });

      // Reset form
      handleClearPhoto();
      setNotesInput("");
      setMoistureInput("");

      // Refresh list & history
      loadClusters();
      loadHistory();

      // Return to clusters tab after short delay
      setTimeout(() => {
        setActiveTab("clusters");
        setActiveClusterId(null);
      }, 1500);
    } catch (err: any) {
      const msg = err?.body?.message || err?.message || "Verification failed. Try again.";
      setVerificationFeedback({
        type: "error",
        message: msg,
      });
    } finally {
      setSubmittingVerification(false);
    }
  };

  // Sync offline queue when connection returns
  useEffect(() => {
    if (isOnline && offlineQueue.length > 0) {
      const syncQueue = async () => {
        const remaining: OfflineVerification[] = [];
        for (const item of offlineQueue) {
          try {
            // Convert base64 back to Blob
            const byteString = atob(item.photo_base64.split(",")[1] || item.photo_base64);
            const ab = new ArrayBuffer(byteString.length);
            const ia = new Uint8Array(ab);
            for (let i = 0; i < byteString.length; i++) {
              ia[i] = byteString.charCodeAt(i);
            }
            const blob = new Blob([ab], { type: item.photo_type });

            const formData = new FormData();
            formData.append("grade", item.grade);
            if (item.moisture_pct) formData.append("moisture_pct", item.moisture_pct);
            if (item.notes) formData.append("notes", item.notes);
            if (item.lat && item.lon) {
              formData.append("lat", item.lat);
              formData.append("lon", item.lon);
            }
            formData.append("photo", blob, item.photo_name);

            await api.postForm(`/api/agent/clusters/${item.cluster_id}/verify`, formData);
          } catch {
            remaining.push(item);
          }
        }
        setOfflineQueue(remaining);
        try {
          localStorage.setItem("offline_verifications", JSON.stringify(remaining));
        } catch {}
        if (remaining.length === 0) {
          loadClusters();
          loadHistory();
        }
      };
      syncQueue();
    }
  }, [isOnline, offlineQueue, loadClusters, loadHistory]);

  // ---------------------------------------------------------------------------
  // Render: Login Screen (if unauthenticated)
  // ---------------------------------------------------------------------------

  if (!token || !agent) {
    return (
      <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col justify-center items-center px-4 py-8 font-sans">
        <div className="w-full max-w-sm bg-slate-800 border border-slate-700 rounded-2xl p-6 shadow-2xl">
          {/* Brand header */}
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-emerald-500/20 text-emerald-400 mb-3 border border-emerald-500/30">
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white">Annadata Dhwani</h1>
            <p className="text-sm text-emerald-400 font-medium">FPO Field Agent Portal</p>
          </div>

          {/* Login Form */}
          <form onSubmit={handleLogin} className="space-y-4">
            {loginError && (
              <div className="bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs p-3 rounded-xl">
                {loginError}
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">
                Registered Phone
              </label>
              <input
                type="tel"
                value={phoneInput}
                onChange={(e) => setPhoneInput(e.target.value)}
                placeholder="+919800000101"
                required
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-white text-base focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">
                4-Digit Security PIN
              </label>
              <input
                type="password"
                maxLength={6}
                value={pinInput}
                onChange={(e) => setPinInput(e.target.value)}
                placeholder="••••"
                required
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-white text-base tracking-widest text-center focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>

            <button
              type="submit"
              disabled={loginLoading}
              className="w-full bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 text-white font-semibold py-3.5 px-4 rounded-xl shadow-lg transition-all flex items-center justify-center space-x-2 disabled:opacity-50"
            >
              {loginLoading ? (
                <>
                  <svg className="animate-spin h-5 w-5 text-white" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <span>Verifying PIN...</span>
                </>
              ) : (
                <span>Agent Login</span>
              )}
            </button>
          </form>

          {/* Quick Demo Pre-fills */}
          <div className="mt-6 pt-4 border-t border-slate-700/60 text-center">
            <p className="text-xs text-slate-400 mb-2">Demo Credentials:</p>
            <div className="flex justify-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setPhoneInput("+919800000101");
                  setPinInput("1234");
                }}
                className="text-xs bg-slate-700/50 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded-lg border border-slate-600"
              >
                Kavya (+919800000101)
              </button>
              <button
                type="button"
                onClick={() => {
                  setPhoneInput("+919800000102");
                  setPinInput("1234");
                }}
                className="text-xs bg-slate-700/50 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded-lg border border-slate-600"
              >
                Suresh (+919800000102)
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Main Field Agent PWA UI
  // ---------------------------------------------------------------------------

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans max-w-md mx-auto shadow-2xl pb-20">
      {/* Offline Alert Banner */}
      {!isOnline && (
        <div className="bg-amber-500 text-slate-950 px-4 py-2 text-xs font-semibold flex items-center justify-between sticky top-0 z-50 shadow">
          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-950 animate-ping" />
            <span>OFFLINE MODE — Verifications will queue locally</span>
          </div>
          {offlineQueue.length > 0 && (
            <span className="bg-slate-950 text-amber-400 px-2 py-0.5 rounded-full text-[10px]">
              {offlineQueue.length} queued
            </span>
          )}
        </div>
      )}

      {/* Top Header */}
      <header className="bg-slate-900 border-b border-slate-800 px-4 py-3 flex items-center justify-between sticky top-0 z-40">
        <div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
            <h1 className="text-base font-bold text-white tracking-tight">Annadata Agent</h1>
          </div>
          <p className="text-xs text-slate-400">
            {agent.name} • {agent.phone}
          </p>
        </div>

        <div className="flex items-center space-x-2">
          {installPrompt && (
            <button
              onClick={() => {
                installPrompt.prompt();
                setInstallPrompt(null);
              }}
              className="bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 text-xs px-2.5 py-1 rounded-lg"
            >
              Install App
            </button>
          )}
          <button
            onClick={handleLogout}
            title="Log out"
            className="text-slate-400 hover:text-rose-400 p-1.5 rounded-lg border border-slate-800 hover:border-slate-700 bg-slate-800/50"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 p-4 space-y-4">
        {/* TAB 1: CLUSTERS WAITING FOR VERIFICATION */}
        {activeTab === "clusters" && (
          <div className="space-y-4">
            {/* Collection point filter */}
            <div className="bg-slate-900 p-3 rounded-2xl border border-slate-800 space-y-2">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                FPO Collection Point
              </label>
              <select
                value={selectedCpId}
                onChange={(e) => setSelectedCpId(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                <option value="all">All Yards ({clusters.length} clusters)</option>
                {collectionPoints.map((cp) => (
                  <option key={cp.id} value={cp.id}>
                    {cp.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Clusters List Header */}
            <div className="flex items-center justify-between px-1">
              <h2 className="text-sm font-semibold text-slate-300">
                Ready for Verification ({clusters.filter((c) => c.status === "READY").length})
              </h2>
              <button
                onClick={loadClusters}
                className="text-xs text-emerald-400 hover:underline flex items-center space-x-1"
              >
                <span>Refresh</span>
              </button>
            </div>

            {/* Clusters Cards */}
            {clustersLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-28 bg-slate-900/60 rounded-2xl animate-pulse border border-slate-800" />
                ))}
              </div>
            ) : clustersError ? (
              <div className="bg-rose-500/10 border border-rose-500/30 text-rose-400 p-4 rounded-2xl text-center text-sm">
                {clustersError}
              </div>
            ) : clusters.length === 0 ? (
              <div className="bg-slate-900/50 border border-slate-800/80 rounded-2xl p-8 text-center text-slate-400 space-y-2">
                <svg className="w-12 h-12 mx-auto text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                </svg>
                <p className="font-medium text-slate-300">No clusters waiting</p>
                <p className="text-xs text-slate-500">Farmers will pool 2–5 tonne clusters via missed-call IVR.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {clusters.map((cluster) => {
                  const isOpen = cluster.status === "READY";            // READY = waiting for the agent to verify the sample
                  return (
                    <div
                      key={cluster.id}
                      className={`p-4 rounded-2xl border transition-all ${
                        isOpen
                          ? "bg-slate-900 border-slate-700/80 hover:border-emerald-500/60 shadow-lg"
                          : "bg-slate-900/40 border-slate-800 opacity-70"
                      }`}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className="text-base font-bold text-white uppercase tracking-wide">
                              {cluster.crop_code.replace("_", " ")}
                            </span>
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${
                                isOpen
                                  ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                                  : "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                              }`}
                            >
                              {cluster.status}
                            </span>
                          </div>
                          <p className="text-xs text-slate-400 mt-0.5">{cluster.collection_point_name}</p>
                        </div>

                        <div className="text-right">
                          <span className="text-xl font-extrabold text-emerald-400">
                            {cluster.total_qtl}{" "}
                            <span className="text-xs font-normal text-slate-400">qtl</span>
                          </span>
                          <p className="text-[11px] text-slate-400">
                            {cluster.listing_count} farmer{cluster.listing_count > 1 ? "s" : ""}
                          </p>
                        </div>
                      </div>

                      {/* Pricing summary */}
                      <div className="bg-slate-950/60 rounded-xl p-2.5 flex justify-between items-center text-xs mb-3 border border-slate-800">
                        <div>
                          <span className="text-slate-400">Weighted Ask:</span>{" "}
                          <span className="font-semibold text-slate-200">₹{cluster.wavg_ask}/qtl</span>
                        </div>
                        <div>
                          <span className="text-slate-400">Min Ask:</span>{" "}
                          <span className="font-semibold text-slate-200">₹{cluster.min_ask}/qtl</span>
                        </div>
                      </div>

                      {/* Action Button */}
                      {isOpen ? (
                        <button
                          onClick={() => {
                            setActiveClusterId(cluster.id);
                            setActiveTab("inspect");
                            setVerificationFeedback(null);
                          }}
                          className="w-full bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 text-white font-semibold py-2.5 px-4 rounded-xl shadow text-sm flex items-center justify-center space-x-2 transition-all"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                          </svg>
                          <span>Inspect & Verify Cluster</span>
                        </button>
                      ) : cluster.status === "OPEN" ? (
                        <div className="text-center text-xs text-slate-500 font-medium py-1">
                          Still collecting: {cluster.total_qtl} of 20 qtl needed
                        </div>
                      ) : (
                        <div className="text-center text-xs text-slate-500 font-medium py-1">
                          Verified Grade: <span className="text-emerald-400 font-bold">{cluster.grade || "–"}</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* TAB 2: INSPECTION & VERIFICATION FORM */}
        {activeTab === "inspect" && (
          <div className="space-y-4">
            {/* Back button */}
            <button
              onClick={() => {
                setActiveTab("clusters");
                setActiveClusterId(null);
                handleClearPhoto();
              }}
              className="text-xs text-slate-400 hover:text-white flex items-center space-x-1"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
              </svg>
              <span>Back to clusters list</span>
            </button>

            {detailLoading ? (
              <div className="h-64 bg-slate-900 rounded-2xl animate-pulse border border-slate-800" />
            ) : !clusterDetail ? (
              <div className="bg-slate-900 p-6 rounded-2xl text-center text-slate-400">
                Please select a cluster to inspect from the Clusters tab.
              </div>
            ) : (
              <form onSubmit={handleSubmitVerification} className="space-y-4">
                {/* Cluster Metadata Card */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow space-y-3">
                  <div className="flex justify-between items-start">
                    <div>
                      <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider">
                        Physical Inspection
                      </span>
                      <h2 className="text-lg font-bold text-white capitalize">
                        {clusterDetail.crop_code.replace("_", " ")} ({clusterDetail.total_qtl} Quintals)
                      </h2>
                      <p className="text-xs text-slate-400">{clusterDetail.collection_point_name}</p>
                    </div>
                    <span className="text-xs bg-slate-800 text-slate-300 font-mono px-2 py-1 rounded">
                      {clusterDetail.id.slice(0, 8)}...
                    </span>
                  </div>

                  {/* Farmer Breakdown Accordion */}
                  <div className="border-t border-slate-800 pt-3">
                    <p className="text-xs font-semibold text-slate-300 mb-2">
                      Pooled Farmers ({clusterDetail.listings.length}):
                    </p>
                    <div className="max-h-36 overflow-y-auto space-y-1.5 pr-1">
                      {clusterDetail.listings.map((l) => (
                        <div
                          key={l.id}
                          className="bg-slate-950 p-2 rounded-xl text-xs flex justify-between items-center border border-slate-800/80"
                        >
                          <div>
                            <span className="font-medium text-slate-200">{l.farmer_name}</span>
                            <span className="text-slate-400 text-[11px] block">{l.village}</span>
                          </div>
                          <div className="text-right">
                            <span className="font-bold text-emerald-400">{l.qty_qtl} qtl</span>
                            <span className="text-slate-400 text-[11px] block">₹{l.ask_price}/qtl</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Form Feedback Alert */}
                {verificationFeedback && (
                  <div
                    className={`p-3.5 rounded-2xl text-xs font-medium border ${
                      verificationFeedback.type === "success"
                        ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                        : "bg-rose-500/10 border-rose-500/30 text-rose-300"
                    }`}
                  >
                    {verificationFeedback.message}
                  </div>
                )}

                {/* Live Camera Photo Capture */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3">
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Produce Photograph (Live Camera) *
                  </label>

                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    capture="environment"
                    onChange={handlePhotoSelect}
                    className="hidden"
                    id="camera-input"
                  />

                  {photoPreview ? (
                    <div className="relative rounded-xl overflow-hidden border border-slate-700 aspect-video bg-black flex items-center justify-center">
                      <img src={photoPreview} alt="Captured Produce" className="max-h-full object-contain" />
                      <button
                        type="button"
                        onClick={handleClearPhoto}
                        className="absolute top-2 right-2 bg-rose-600/80 hover:bg-rose-600 text-white p-1.5 rounded-full shadow"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  ) : (
                    <label
                      htmlFor="camera-input"
                      className="border-2 border-dashed border-slate-700 hover:border-emerald-500/60 rounded-xl p-6 flex flex-col items-center justify-center space-y-2 cursor-pointer bg-slate-950/40 active:bg-slate-800"
                    >
                      <div className="w-12 h-12 rounded-full bg-emerald-500/10 text-emerald-400 flex items-center justify-center border border-emerald-500/20">
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                      </div>
                      <span className="text-sm font-semibold text-slate-200">Tap to Capture Produce Photo</span>
                      <span className="text-[11px] text-slate-500">Take clear shot of grain color and cleanliness</span>
                    </label>
                  )}
                </div>

                {/* Quality Grade Selection */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-2">
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Quality Grade Assessment *
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { grade: "A", title: "Grade A", desc: "Premium (Clean, dry)" },
                      { grade: "B", title: "Grade B", desc: "Standard (FAQ)" },
                      { grade: "C", title: "Grade C", desc: "Below Standard" },
                    ].map((g) => {
                      const isSelected = selectedGrade === g.grade;
                      return (
                        <button
                          key={g.grade}
                          type="button"
                          onClick={() => setSelectedGrade(g.grade as any)}
                          className={`p-3 rounded-xl border text-center transition-all ${
                            isSelected
                              ? "bg-emerald-600 text-white border-emerald-400 shadow-md"
                              : "bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200"
                          }`}
                        >
                          <span className="block text-base font-bold">{g.title}</span>
                          <span className="text-[10px] opacity-80">{g.desc}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Moisture % and Observations */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3">
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">
                      Moisture Content (%)
                    </label>
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      max="40"
                      placeholder="e.g. 11.5"
                      value={moistureInput}
                      onChange={(e) => setMoistureInput(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">
                      Inspection Notes
                    </label>
                    <textarea
                      rows={2}
                      placeholder="e.g. Grain bagged in clean jute bags, no weevil infestation"
                      value={notesInput}
                      onChange={(e) => setNotesInput(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                    />
                  </div>
                </div>

                {/* Submit Verification Button */}
                <button
                  type="submit"
                  disabled={submittingVerification}
                  className="w-full bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 text-white font-bold py-3.5 px-4 rounded-2xl shadow-xl transition-all flex items-center justify-center space-x-2 disabled:opacity-50"
                >
                  {submittingVerification ? (
                    <>
                      <svg className="animate-spin h-5 w-5 text-white" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                      </svg>
                      <span>Submitting Verification...</span>
                    </>
                  ) : (
                    <span>Submit Physical Verification</span>
                  )}
                </button>
              </form>
            )}
          </div>
        )}

        {/* TAB 3: VERIFICATION HISTORY */}
        {activeTab === "history" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between px-1">
              <h2 className="text-sm font-semibold text-slate-300">
                Verified by You ({historyItems.length})
              </h2>
              <button
                onClick={loadHistory}
                className="text-xs text-emerald-400 hover:underline flex items-center space-x-1"
              >
                <span>Refresh</span>
              </button>
            </div>

            {historyLoading ? (
              <div className="space-y-3">
                {[1, 2].map((i) => (
                  <div key={i} className="h-24 bg-slate-900 rounded-2xl animate-pulse border border-slate-800" />
                ))}
              </div>
            ) : historyItems.length === 0 ? (
              <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-8 text-center text-slate-400">
                <p>No verification history found.</p>
                <p className="text-xs text-slate-500 mt-1">Inspections you complete will appear here.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {historyItems.map((item) => (
                  <div
                    key={item.id}
                    className="bg-slate-900 border border-slate-800 rounded-2xl p-3.5 flex items-center space-x-3 shadow"
                  >
                    {/* Photo thumbnail */}
                    <div className="w-16 h-16 rounded-xl bg-slate-950 overflow-hidden border border-slate-800 flex-shrink-0">
                      {item.photo_url ? (
                        <img
                          src={item.photo_url}
                          alt="Verified Produce"
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            // Fallback icon on broken image
                            (e.target as any).style.display = "none";
                          }}
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-slate-600">
                          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                          </svg>
                        </div>
                      )}
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center space-x-2">
                        <span className="text-sm font-bold text-white uppercase truncate">
                          {item.crop_code.replace("_", " ")}
                        </span>
                        <span className="bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[10px] font-bold px-2 py-0.5 rounded-full">
                          Grade {item.grade}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400">
                        {item.total_qtl} qtl • {item.moisture_pct ? `${item.moisture_pct}% moisture` : "Dry"}
                      </p>
                      <p className="text-[11px] text-slate-500 truncate mt-0.5">
                        {new Date(item.verified_at).toLocaleDateString()} at{" "}
                        {new Date(item.verified_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      {/* Bottom Sticky Tab Navigation */}
      <nav className="fixed bottom-0 left-0 right-0 max-w-md mx-auto bg-slate-900 border-t border-slate-800 px-4 py-2 flex justify-around items-center z-40">
        <button
          onClick={() => setActiveTab("clusters")}
          className={`flex flex-col items-center space-y-1 py-1 px-3 rounded-xl transition-all ${
            activeTab === "clusters" ? "text-emerald-400 font-semibold" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
          <span className="text-[11px]">Clusters</span>
        </button>

        <button
          onClick={() => {
            if (!activeClusterId && clusters.length > 0) {
              const openCluster = clusters.find((c) => c.status === "READY") || clusters[0];
              setActiveClusterId(openCluster.id);
            }
            setActiveTab("inspect");
          }}
          className={`flex flex-col items-center space-y-1 py-1 px-3 rounded-xl transition-all ${
            activeTab === "inspect" ? "text-emerald-400 font-semibold" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="text-[11px]">Inspect</span>
        </button>

        <button
          onClick={() => setActiveTab("history")}
          className={`flex flex-col items-center space-y-1 py-1 px-3 rounded-xl transition-all ${
            activeTab === "history" ? "text-emerald-400 font-semibold" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="text-[11px]">History</span>
        </button>
      </nav>
    </div>
  );
}
