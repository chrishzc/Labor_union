/** Prefix same-origin API requests for the optional Windows remote entry. */
export function applicationUrl(path: string): string {
  const prefix = import.meta.env.VITE_PUBLIC_PATH_PREFIX || '';
  return prefix && path.startsWith('/api/') ? `${prefix}${path}` : path;
}

export function applicationFetch(path: string, options?: RequestInit): Promise<Response> {
  return fetch(applicationUrl(path), options);
}
