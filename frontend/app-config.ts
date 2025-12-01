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
  companyName: 'Amazon Voice Shopping',
  pageTitle: 'Amazon Voice Shopping - AI Shopping Assistant',
  pageDescription: 'Shop smarter with voice. Your AI-powered shopping assistant for finding products, managing your cart, and completing purchases hands-free.',
  supportsChatInput: true,
  supportsVideoInput: false,
  supportsScreenShare: false,
  isPreConnectBufferEnabled: true,

  logo: '🛒',
  accent: '#FF9900',
  logoDark: '🛒',
  accentDark: '#FFB84D',
  startButtonText: 'Start Voice Shopping',

  // for LiveKit Cloud Sandbox
  sandboxId: undefined,
  agentName: undefined,
};

