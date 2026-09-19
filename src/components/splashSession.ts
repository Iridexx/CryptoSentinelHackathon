export const SPLASH_SESSION_KEY = 'cs_splash_shown';

export function shouldShowSplash(): boolean {
  return !sessionStorage.getItem(SPLASH_SESSION_KEY);
}
