import {
    forwardRef, useEffect, useImperativeHandle, useRef, useState, useCallback,
} from "react";
import Hls from "hls.js";
import {
    Play, Pause, Volume2, VolumeX, Maximize, Minimize,
    PictureInPicture2, Subtitles, Settings, SkipForward, SkipBack,
} from "lucide-react";

interface SubtitleTrack {
    id: number;
    name: string;
    lang: string;
}

interface VideoPlayerProps {
    src: string;
}

function formatTime(seconds: number): string {
    if (!isFinite(seconds)) return "0:00";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    return `${m}:${String(s).padStart(2, "0")}`;
}

const VideoPlayer = forwardRef<HTMLVideoElement, VideoPlayerProps>(
    function VideoPlayer({ src }, externalRef) {
        const videoRef = useRef<HTMLVideoElement>(null);
        const containerRef = useRef<HTMLDivElement>(null);
        const hlsRef = useRef<Hls | null>(null);
        const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

        const [error, setError] = useState(false);
        const [playing, setPlaying] = useState(false);
        const [muted, setMuted] = useState(false);
        const [volume, setVolume] = useState(1);
        const [currentTime, setCurrentTime] = useState(0);
        const [duration, setDuration] = useState(0);
        const [buffered, setBuffered] = useState(0);
        const [fullscreen, setFullscreen] = useState(false);
        const [pip, setPip] = useState(false);
        const [controlsVisible, setControlsVisible] = useState(true);
        const [subtitleTracks, setSubtitleTracks] = useState<SubtitleTrack[]>([]);
        const [activeSubtitle, setActiveSubtitle] = useState<number>(-1); // -1 = off
        const [showSubMenu, setShowSubMenu] = useState(false);
        const [showQualityMenu, setShowQualityMenu] = useState(false);
        const [qualityLevels, setQualityLevels] = useState<{ id: number; label: string }[]>([]);
        const [activeQuality, setActiveQuality] = useState<number>(-1);

        useImperativeHandle(externalRef, () => videoRef.current as HTMLVideoElement, []);

        // ── HLS setup ──────────────────────────────────────────────────────────
        useEffect(() => {
            setError(false);
            setPlaying(false);
            setCurrentTime(0);
            setDuration(0);
            setSubtitleTracks([]);
            setActiveSubtitle(-1);

            const video = videoRef.current;
            if (!video || !src) return;

            if (Hls.isSupported()) {
                const hls = new Hls({ enableWorker: true });
                hlsRef.current = hls;
                hls.loadSource(src);
                hls.attachMedia(video);

                hls.on(Hls.Events.MANIFEST_PARSED, (_e, data) => {
                    const levels = data.levels.map((l, i) => ({
                        id: i,
                        label: l.height ? `${l.height}p` : `Level ${i}`,
                    }));
                    setQualityLevels(levels);
                    setActiveQuality(-1);
                });

                hls.on(Hls.Events.SUBTITLE_TRACKS_UPDATED, (_e, data) => {
                    const tracks: SubtitleTrack[] = data.subtitleTracks.map((t) => ({
                        id: t.id,
                        name: t.name || t.lang || `Track ${t.id}`,
                        lang: t.lang || "",
                    }));
                    setSubtitleTracks(tracks);
                });

                hls.on(Hls.Events.SUBTITLE_TRACK_SWITCH, (_e, data) => {
                    setActiveSubtitle(data.id ?? -1);
                });

                hls.on(Hls.Events.ERROR, (_event, d) => {
                    if (d.fatal) { setError(true); hls.destroy(); }
                });

                return () => { hls.destroy(); hlsRef.current = null; };
            } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
                video.src = src;
            }
        }, [src]);

        // ── Native video events ────────────────────────────────────────────────
        useEffect(() => {
            const video = videoRef.current;
            if (!video) return;

            const onPlay = () => setPlaying(true);
            const onPause = () => setPlaying(false);
            const onTimeUpdate = () => {
                setCurrentTime(video.currentTime);
                if (video.buffered.length > 0) {
                    setBuffered(video.buffered.end(video.buffered.length - 1));
                }
            };
            const onDurationChange = () => setDuration(video.duration);
            const onVolumeChange = () => { setVolume(video.volume); setMuted(video.muted); };
            const onEnterPiP = () => setPip(true);
            const onLeavePiP = () => setPip(false);

            video.addEventListener("play", onPlay);
            video.addEventListener("pause", onPause);
            video.addEventListener("timeupdate", onTimeUpdate);
            video.addEventListener("durationchange", onDurationChange);
            video.addEventListener("volumechange", onVolumeChange);
            video.addEventListener("enterpictureinpicture", onEnterPiP);
            video.addEventListener("leavepictureinpicture", onLeavePiP);

            return () => {
                video.removeEventListener("play", onPlay);
                video.removeEventListener("pause", onPause);
                video.removeEventListener("timeupdate", onTimeUpdate);
                video.removeEventListener("durationchange", onDurationChange);
                video.removeEventListener("volumechange", onVolumeChange);
                video.removeEventListener("enterpictureinpicture", onEnterPiP);
                video.removeEventListener("leavepictureinpicture", onLeavePiP);
            };
        }, []);

        // ── Fullscreen change ─────────────────────────────────────────────────
        useEffect(() => {
            const onFsChange = () => setFullscreen(!!document.fullscreenElement);
            document.addEventListener("fullscreenchange", onFsChange);
            return () => document.removeEventListener("fullscreenchange", onFsChange);
        }, []);

        // ── Controls auto-hide ────────────────────────────────────────────────
        const showControls = useCallback(() => {
            setControlsVisible(true);
            if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
            hideTimerRef.current = setTimeout(() => {
                if (videoRef.current && !videoRef.current.paused) setControlsVisible(false);
            }, 3000);
        }, []);

        // ── Actions ───────────────────────────────────────────────────────────
        const togglePlay = () => {
            const v = videoRef.current;
            if (!v) return;
            v.paused ? v.play() : v.pause();
        };

        const toggleMute = () => {
            const v = videoRef.current;
            if (!v) return;
            v.muted = !v.muted;
        };

        const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
            const v = videoRef.current;
            if (!v) return;
            const val = parseFloat(e.target.value);
            v.volume = val;
            v.muted = val === 0;
        };

        const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
            const v = videoRef.current;
            if (!v) return;
            v.currentTime = parseFloat(e.target.value);
        };

        const skip = (seconds: number) => {
            const v = videoRef.current;
            if (!v) return;
            v.currentTime = Math.max(0, Math.min(v.duration, v.currentTime + seconds));
        };

        const toggleFullscreen = () => {
            const el = containerRef.current;
            if (!el) return;
            if (!document.fullscreenElement) {
                el.requestFullscreen();
            } else {
                document.exitFullscreen();
            }
        };

        const togglePiP = async () => {
            const v = videoRef.current;
            if (!v) return;
            if (document.pictureInPictureElement) {
                await document.exitPictureInPicture();
            } else {
                await v.requestPictureInPicture();
            }
        };

        const selectSubtitle = (id: number) => {
            if (!hlsRef.current) return;
            if (id === -1) {
                hlsRef.current.subtitleTrack = -1;
                setActiveSubtitle(-1);
            } else {
                hlsRef.current.subtitleTrack = id;
                setActiveSubtitle(id);
            }
            setShowSubMenu(false);
        };

        const selectQuality = (id: number) => {
            if (!hlsRef.current) return;
            hlsRef.current.currentLevel = id;
            setActiveQuality(id);
            setShowQualityMenu(false);
        };

        if (error || !src) {
            return (
                <div
                    className="w-full flex items-center justify-center bg-black text-white/60 text-sm"
                    style={{ aspectRatio: "16/9" }}
                >
                    Video unavailable
                </div>
            );
        }

        const progress = duration > 0 ? (currentTime / duration) * 100 : 0;
        const bufferedPct = duration > 0 ? (buffered / duration) * 100 : 0;

        return (
            <div
                ref={containerRef}
                className="relative w-full bg-black select-none"
                style={{ aspectRatio: "16/9" }}
                onMouseMove={showControls}
                onMouseEnter={showControls}
                onMouseLeave={() => {
                    if (playing) setControlsVisible(false);
                    setShowSubMenu(false);
                    setShowQualityMenu(false);
                }}
                onClick={() => { togglePlay(); showControls(); }}
            >
                {/* Video element — no native controls */}
                <video
                    ref={videoRef}
                    className="w-full h-full"
                    style={{ display: "block" }}
                />

                {/* Controls overlay */}
                <div
                    className={`absolute inset-0 flex flex-col justify-end transition-opacity duration-200 ${
                        controlsVisible ? "opacity-100" : "opacity-0 pointer-events-none"
                    }`}
                    onClick={(e) => e.stopPropagation()}
                >
                    {/* Gradient */}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent pointer-events-none" />

                    {/* Seek bar */}
                    <div className="relative px-3 pb-1 z-10">
                        <div className="relative h-1 rounded-full bg-white/20 cursor-pointer">
                            {/* Buffered */}
                            <div
                                className="absolute inset-y-0 left-0 bg-white/30 rounded-full"
                                style={{ width: `${bufferedPct}%` }}
                            />
                            {/* Played */}
                            <div
                                className="absolute inset-y-0 left-0 bg-red-500 rounded-full"
                                style={{ width: `${progress}%` }}
                            />
                            <input
                                type="range"
                                min={0}
                                max={duration || 100}
                                step={0.1}
                                value={currentTime}
                                onChange={handleSeek}
                                className="absolute inset-0 w-full opacity-0 cursor-pointer h-full"
                            />
                        </div>
                    </div>

                    {/* Bottom row */}
                    <div className="relative z-10 flex items-center gap-1 px-3 pb-2 text-white">
                        {/* Play / Pause */}
                        <button
                            onClick={togglePlay}
                            className="p-1.5 rounded-full hover:bg-white/10 transition-colors"
                            title={playing ? "Pause" : "Play"}
                        >
                            {playing ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5" />}
                        </button>

                        {/* Skip -10 / +10 */}
                        <button
                            onClick={() => skip(-10)}
                            className="p-1.5 rounded-full hover:bg-white/10 transition-colors"
                            title="-10s"
                        >
                            <SkipBack className="h-4 w-4" />
                        </button>
                        <button
                            onClick={() => skip(10)}
                            className="p-1.5 rounded-full hover:bg-white/10 transition-colors"
                            title="+10s"
                        >
                            <SkipForward className="h-4 w-4" />
                        </button>

                        {/* Volume */}
                        <button
                            onClick={toggleMute}
                            className="p-1.5 rounded-full hover:bg-white/10 transition-colors"
                        >
                            {muted || volume === 0 ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
                        </button>
                        <input
                            type="range"
                            min={0}
                            max={1}
                            step={0.05}
                            value={muted ? 0 : volume}
                            onChange={handleVolumeChange}
                            className="w-16 accent-white cursor-pointer"
                        />

                        {/* Time */}
                        <span className="text-xs ml-1 tabular-nums shrink-0">
                            {formatTime(currentTime)} / {formatTime(duration)}
                        </span>

                        <div className="flex-1" />

                        {/* Subtitles button — always visible, grayed out if no tracks */}
                        <div className="relative">
                            <button
                                onClick={() => {
                                    setShowSubMenu((v) => !v);
                                    setShowQualityMenu(false);
                                }}
                                className={`p-1.5 rounded-full transition-colors ${
                                    subtitleTracks.length === 0
                                        ? "opacity-40 cursor-default"
                                        : activeSubtitle >= 0
                                        ? "bg-white/20 hover:bg-white/30"
                                        : "hover:bg-white/10"
                                }`}
                                title={subtitleTracks.length === 0 ? "No subtitles available" : "Subtitles"}
                                disabled={subtitleTracks.length === 0}
                            >
                                <Subtitles className="h-4 w-4" />
                            </button>
                            {showSubMenu && subtitleTracks.length > 0 && (
                                <div className="absolute bottom-full right-0 mb-2 min-w-[140px] rounded-lg bg-black/90 border border-white/10 py-1 text-sm shadow-xl">
                                    <button
                                        onClick={() => selectSubtitle(-1)}
                                        className={`w-full text-left px-3 py-1.5 hover:bg-white/10 transition-colors ${activeSubtitle === -1 ? "text-red-400 font-medium" : ""}`}
                                    >
                                        Off
                                    </button>
                                    {subtitleTracks.map((t) => (
                                        <button
                                            key={t.id}
                                            onClick={() => selectSubtitle(t.id)}
                                            className={`w-full text-left px-3 py-1.5 hover:bg-white/10 transition-colors ${activeSubtitle === t.id ? "text-red-400 font-medium" : ""}`}
                                        >
                                            {t.name}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Quality selector */}
                        {qualityLevels.length > 1 && (
                            <div className="relative">
                                <button
                                    onClick={() => {
                                        setShowQualityMenu((v) => !v);
                                        setShowSubMenu(false);
                                    }}
                                    className="p-1.5 rounded-full hover:bg-white/10 transition-colors"
                                    title="Quality"
                                >
                                    <Settings className="h-4 w-4" />
                                </button>
                                {showQualityMenu && (
                                    <div className="absolute bottom-full right-0 mb-2 min-w-[120px] rounded-lg bg-black/90 border border-white/10 py-1 text-sm shadow-xl">
                                        <button
                                            onClick={() => selectQuality(-1)}
                                            className={`w-full text-left px-3 py-1.5 hover:bg-white/10 transition-colors ${activeQuality === -1 ? "text-red-400 font-medium" : ""}`}
                                        >
                                            Auto
                                        </button>
                                        {qualityLevels.map((l) => (
                                            <button
                                                key={l.id}
                                                onClick={() => selectQuality(l.id)}
                                                className={`w-full text-left px-3 py-1.5 hover:bg-white/10 transition-colors ${activeQuality === l.id ? "text-red-400 font-medium" : ""}`}
                                            >
                                                {l.label}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}

                        {/* PiP */}
                        {document.pictureInPictureEnabled && (
                            <button
                                onClick={togglePiP}
                                className={`p-1.5 rounded-full hover:bg-white/10 transition-colors ${pip ? "bg-white/20" : ""}`}
                                title="Picture in picture"
                            >
                                <PictureInPicture2 className="h-4 w-4" />
                            </button>
                        )}

                        {/* Fullscreen */}
                        <button
                            onClick={toggleFullscreen}
                            className="p-1.5 rounded-full hover:bg-white/10 transition-colors"
                            title={fullscreen ? "Exit fullscreen" : "Fullscreen"}
                        >
                            {fullscreen ? <Minimize className="h-4 w-4" /> : <Maximize className="h-4 w-4" />}
                        </button>
                    </div>
                </div>
            </div>
        );
    },
);

export default VideoPlayer;
