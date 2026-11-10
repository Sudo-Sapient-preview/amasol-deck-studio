import express from "express";
import { handleUpload } from "@vercel/blob/client";

// shortcut: mirrors server/app/config.py MAX_FILE_BYTES by hand (no shared config across the Node/Python boundary)
const MAX_FILE_BYTES = 60 * 1024 * 1024;
const TOKEN_TTL_MS = 10 * 60 * 1000; // short-lived: just long enough for one upload

const app = express();
app.use(express.json());

// No auth: the app has no login today, so uploads stay open (parity with the old server).
app.post("/api/upload", async (req, res) => {
  try {
    const jsonResponse = await handleUpload({
      body: req.body,
      request: req,
      onBeforeGenerateToken: async (pathname) => {
        if (!pathname.startsWith("uploads/") || pathname.includes("..")) {
          throw new Error("Invalid upload path");
        }
        return {
          addRandomSuffix: false,
          maximumSizeInBytes: MAX_FILE_BYTES,
          validUntil: Date.now() + TOKEN_TTL_MS,
        };
      },
      onUploadCompleted: async () => {
        /* nothing to do: the browser posts the finished blob info to /api/jobs itself */
      },
    });
    res.json(jsonResponse);
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
});

export default app;
