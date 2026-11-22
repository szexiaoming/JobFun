import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "JobFun · AI 求职工作台",
    short_name: "JobFun",
    description: "可追溯、不过度编造的 AI 求职工作台",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    background_color: "#f4f7fb",
    theme_color: "#0b1530",
    orientation: "portrait-primary",
    icons: [
      {
        src: "/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
