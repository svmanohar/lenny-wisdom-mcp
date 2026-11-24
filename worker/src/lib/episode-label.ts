interface EpisodeNames {
  title: string | null;
  guest: string | null;
}

/** Episode title, falling back to the guest name, then "Untitled episode". */
export function episodeTitle(ep: EpisodeNames): string {
  return ep.title || ep.guest || "Untitled episode";
}

/** "Title (Guest)" when both exist; never repeats the guest when it stands in for the title. */
export function episodeLabel(ep: EpisodeNames): string {
  if (ep.title && ep.guest) return `${ep.title} (${ep.guest})`;
  return episodeTitle(ep);
}
