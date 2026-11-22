import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.neon.aitrader.ultra",
  appName: "NEON AI TRADER",
  webDir: "dist",
  bundledWebRuntime: false,
  server: {
    androidScheme: "https",
    cleartext: true
  },
  android: {
    backgroundColor: "#000000",
    allowMixedContent: false
  }
};

export default config;
