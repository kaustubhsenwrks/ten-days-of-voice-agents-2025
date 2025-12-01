export interface AppConfig {
  pageTitle: string;
  pageDescription: string;
  companyName: string;

  supportsChatInput: boolean;
  supportsVideoInput: boolean;
  supportsScreenShare: boolean;
  isPreConnectBufferEnabled: boolean;

  logo: string;
  startButtonText: string;
  accent?: string;
  logoDark?: string;
  accentDark?: string;

  // for LiveKit Cloud Sandbox
  sandboxId?: string;
  agentName?: string;
}

export const APP_CONFIG_DEFAULTS: AppConfig = {
  companyName: 'Improv Battle',
  pageTitle: '🎭 Improv Battle – Voice Game Show',
  pageDescription: 'A Day 10 improv challenge voice agent',

  // ⚠ Improv Battle does NOT need chat or video
  supportsChatInput: false,
  supportsVideoInput: false,
  supportsScreenShare: false,
  isPreConnectBufferEnabled: false,

  logo: '/lk-logo.svg',
  accent: '#002cf2',
  logoDark: '/lk-logo-dark.svg',
  accentDark: '#1fd5f9',

  // button text on welcome screen
  startButtonText: 'Start Improv Battle',

  // ⚠ THIS IS THE MOST IMPORTANT PART
  agentName: 'improv-battle-agent',

  // sandbox ID comes from your env
  sandboxId: process.env.NEXT_PUBLIC_LK_SANDBOX_ID,
};