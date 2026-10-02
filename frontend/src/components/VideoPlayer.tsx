import { useCallback, useEffect, useRef, type Ref } from "react";
import { MediaPlayer, MediaProvider, type MediaPlayerInstance } from "@vidstack/react";
import { DefaultVideoLayout, defaultLayoutIcons } from "@vidstack/react/player/layouts/default";

// Shared player for every real (controls-enabled) video surface in the app --
// Vidstack instead of the native <video> element, for real control over the
// control bar (skinned to the app's own theme via --media-* CSS variables in
// index.css, playback-speed menu built in) rather than whatever the OS/browser
// happens to render. Decorative, controls-less preview thumbnails (card
// hover-posters, the tiny collapsed-row thumbnail) intentionally stay native
// <video> -- a full player is unnecessary weight for something that's just a
// muted background image.
export default function VideoPlayer({
  src,
  className,
  muted,
  poster,
  onTimeUpdate,
  controls = true,
  playerRef,
  loop,
  autoPlay,
  clipStart,
  clipEnd,
  onEnded,
  style,
}: {
  src?: string | null;
  className?: string;
  muted?: boolean;
  poster?: string | null;
  onTimeUpdate?: (currentTime: number) => void;
  // Set false for a player that's on screen only as a non-interactive
  // preview (e.g. an unselected carousel neighbor) -- the control-bar icons
  // are visual noise on a card nothing inside is clickable on.
  controls?: boolean;
  // Handle on the Vidstack player (play(), pause(), currentTime) for callers that drive several players at once.
  playerRef?: Ref<MediaPlayerInstance>;
  loop?: boolean;
  autoPlay?: boolean;
  // Play only a stretch of one longer file (seconds): a scene of the uploaded source video.
  clipStart?: number;
  clipEnd?: number;
  onEnded?: () => void;
  style?: React.ComponentProps<typeof MediaPlayer>["style"];
}) {
  const player = useRef<MediaPlayerInstance | null>(null);
  const setPlayer = useCallback(
    (instance: MediaPlayerInstance | null) => {
      player.current = instance;
      if (typeof playerRef === "function") playerRef(instance);
      else if (playerRef) (playerRef as { current: MediaPlayerInstance | null }).current = instance;
    },
    [playerRef],
  );

  useEffect(() => {
    if (!onTimeUpdate) return;
    return player.current?.subscribe(({ currentTime }) => onTimeUpdate(currentTime));
  }, [onTimeUpdate]);

  if (!src) return null;

  return (
    <MediaPlayer
      ref={setPlayer}
      src={src}
      muted={muted}
      poster={poster ?? undefined}
      playsInline
      // Only pass what was asked for: Vidstack treats an explicit undefined clip time as a clip of nothing ("LIVE").
      {...(loop !== undefined ? { loop } : {})}
      {...(autoPlay !== undefined ? { autoPlay } : {})}
      {...(clipStart !== undefined ? { clipStartTime: clipStart } : {})}
      {...(clipEnd !== undefined ? { clipEndTime: clipEnd } : {})}
      // onEnd also fires at a clip's end; the native ended event never does for a stretch of a longer file.
      {...(onEnded ? { onEnd: onEnded } : {})}
      className={className}
      style={style}
      // Vidstack's default 2s idle delay is tuned for long-form video --
      // these clips are only a few seconds long, so controls should tuck
      // away almost as soon as playback starts rather than lingering over
      // most of the clip.
      controlsDelay={500}
    >
      <MediaProvider />
      {controls && (
        <DefaultVideoLayout
          icons={defaultLayoutIcons}
          slots={{ googleCastButton: null }}
          // Vidstack swaps to a cramped "small" layout (vertical volume
          // popup, controls split across extra rows) below 380px tall --
          // every player in this app is embedded well under that, so left
          // alone it was the small layout everywhere, never the large one.
          // Forcing the large layout keeps one predictable, orderly control
          // bar regardless of how small the embed is.
          smallLayoutWhen={false}
        />
      )}
    </MediaPlayer>
  );
}
