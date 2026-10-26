/** Keep the resolved file location readable without changing the filesystem path. */
export function displayConfigPath(path: string): string {
  const prefix = '\\\\?\\';
  if (!path.startsWith(prefix)) return path;
  const rest = path.slice(prefix.length);
  if (rest.startsWith('UNC\\')) return '\\\\' + rest.slice(4);
  return /^[a-z]:\\/i.test(rest) ? rest : path;
}
