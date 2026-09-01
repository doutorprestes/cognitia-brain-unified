import { exec } from "node:child_process";
import { promisify } from "node:util";
import express from "express";
import multer from "multer";
import { join } from "node:path";
import { readFile, writeFile, copyFile, mkdir } from "node:fs/promises";
import { timingSafeEqual } from "node:crypto";
import { GoogleGenerativeAI, SchemaType } from "@google/generative-ai";

const execAsync = promisify(exec);

const app = express();
const upload = multer({ dest: "/tmp/uploads/", limits: { fileSize: 10 * 1024 * 1024 } });

const DATA_DIR = process.env.DATA_DIR || "data";
const STATIC_DIR = process.env.STATIC_DIR || "frontend/dist";
const PORT = Number(process.env.PORT) || 8000;
const HOST = process.env.HOST || "0.0.0.0";

// ── HTTP Basic Auth ──────────────────────────────────────────────
const AUTH_USER = process.env.GRANTWATCH_USER || "admin";
const AUTH_PASS = process.env.GRANTWATCH_PASSWORD || "";
const AUTH_ENABLED = AUTH_PASS.length > 0;

function basicAuth(req: express.Request, res: express.Response, next: express.NextFunction) {
  if (!AUTH_ENABLED) return next(); // skip if no password set

  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith("Basic ")) {
    res.setHeader("WWW-Authenticate", 'Basic realm="GrantWatch", charset="UTF-8"');
    return res.status(401).send("Authentication required");
  }

  const [user, pass] = Buffer.from(authHeader.slice(6), "base64").toString("utf8").split(":");
  const userOk = Buffer.from(user).length === Buffer.from(AUTH_USER).length &&
    timingSafeEqual(Buffer.from(user), Buffer.from(AUTH_USER));
  const passOk = Buffer.from(pass).length === Buffer.from(AUTH_PASS).length &&
    timingSafeEqual(Buffer.from(pass), Buffer.from(AUTH_PASS));

  if (!userOk || !passOk) {
    res.setHeader("WWW-Authenticate", 'Basic realm="GrantWatch", charset="UTF-8"');
    return res.status(401).send("Invalid credentials");
  }

  next();
}

app.use(express.json());
app.use(basicAuth);

// Serve frontend static files (protected by basicAuth above)
app.use(express.static(STATIC_DIR));

// API Routes
app.get("/api/opportunities", async (_req, res) => {
  try {
    const data = await readFile(join(DATA_DIR, "static-api", "opportunities.json"), "utf8");
    res.json(JSON.parse(data));
  } catch {
    res.status(500).json({ error: "Opportunities not available" });
  }
});

app.get("/api/status", async (_req, res) => {
  try {
    const data = await readFile(join(DATA_DIR, "static-api", "status.json"), "utf8");
    res.json(JSON.parse(data));
  } catch {
    res.status(500).json({ error: "Status not available" });
  }
});

app.get("/api/profile", async (_req, res) => {
  try {
    const data = await readFile(join(DATA_DIR, "mestrado_profile_requirements.json"), "utf8");
    res.json(JSON.parse(data));
  } catch {
    res.status(500).json({ error: "Profile not available" });
  }
});

app.get("/api/changelog", async (_req, res) => {
  try {
    const data = await readFile(join(DATA_DIR, "static-api", "changelog.md"), "utf8");
    res.type("text/markdown").send(data);
  } catch {
    res.status(500).send("Changelog not available");
  }
});

app.put("/api/profile", async (req, res) => {
  try {
    await writeFile(join(DATA_DIR, "mestrado_profile_requirements.json"), JSON.stringify(req.body, null, 2) + "\n", "utf8");
    res.json({ success: true });
  } catch {
    res.status(500).json({ error: "Failed to save profile" });
  }
});

const profileSchema = {
  description: "Extract a research project profile for grant/opportunity matching",
  type: SchemaType.OBJECT,
  properties: {
    profile_id: { type: SchemaType.STRING, description: "Unique profile identifier (e.g., feec_unicamp_marl_morphic_field_v4)" },
    objective: { type: SchemaType.STRING, description: "Concise research objective (1-2 sentences)" },
    hard_filters: {
      type: SchemaType.OBJECT,
      properties: {
        include_any_technical_core: { type: SchemaType.ARRAY, items: { type: SchemaType.STRING }, description: "Technical terms that must appear in the opportunity" },
        include_any_application_context: { type: SchemaType.ARRAY, items: { type: SchemaType.STRING }, description: "Application context terms (robotics, startup, etc.)" },
        required_audience_any: { type: SchemaType.ARRAY, items: { type: SchemaType.STRING }, description: "Eligible audience terms (researcher, student, etc.)" },
        exclude_any: { type: SchemaType.ARRAY, items: { type: SchemaType.STRING }, description: "Terms that should exclude an opportunity" },
        soft_exclude_any: { type: SchemaType.ARRAY, items: { type: SchemaType.STRING }, description: "Terms that lightly penalize but don't exclude" },
        deadline_min_days: { type: SchemaType.NUMBER, description: "Minimum days before deadline to consider" },
      },
      required: ["include_any_technical_core", "include_any_application_context", "required_audience_any", "exclude_any", "deadline_min_days"],
    },
    scoring: {
      type: SchemaType.OBJECT,
      properties: {
        weights: {
          type: SchemaType.OBJECT,
          properties: {
            thematic_fit: { type: SchemaType.NUMBER },
            eligibility_fit: { type: SchemaType.NUMBER },
            methodological_fit: { type: SchemaType.NUMBER },
            timeline_fit: { type: SchemaType.NUMBER },
            resource_fit: { type: SchemaType.NUMBER },
          },
          required: ["thematic_fit", "eligibility_fit", "methodological_fit", "timeline_fit", "resource_fit"],
        },
        thresholds: {
          type: SchemaType.OBJECT,
          properties: {
            go: { type: SchemaType.NUMBER },
            watch: { type: SchemaType.NUMBER },
          },
          required: ["go", "watch"],
        },
        thematic_fit_terms: {
          type: SchemaType.OBJECT,
          properties: {
            high: { type: SchemaType.ARRAY, items: { type: SchemaType.STRING } },
            medium: { type: SchemaType.ARRAY, items: { type: SchemaType.STRING } },
            low: { type: SchemaType.ARRAY, items: { type: SchemaType.STRING } },
          },
          required: ["high", "medium", "low"],
        },
        methodological_fit_terms: { type: SchemaType.ARRAY, items: { type: SchemaType.STRING } },
        resource_fit_terms: { type: SchemaType.ARRAY, items: { type: SchemaType.STRING } },
      },
      required: ["weights", "thresholds", "thematic_fit_terms"],
    },
    required_output_fields: {
      type: SchemaType.ARRAY,
      items: { type: SchemaType.STRING },
      description: "Required fields for pipeline output",
    },
  },
  required: ["profile_id", "objective", "hard_filters", "scoring", "required_output_fields"],
} as const;

app.post("/api/analyze-profile-pdf", upload.single("pdf"), async (req, res) => {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey || apiKey === "sua_chave_aqui") {
    res.status(503).json({ error: "GEMINI_API_KEY not configured" });
    return;
  }

  if (!req.file) {
    res.status(400).json({ error: "No PDF uploaded" });
    return;
  }

  try {
    const genAI = new GoogleGenerativeAI(apiKey);
    const model = genAI.getGenerativeModel({
      model: "gemini-2.5-flash-lite",
      generationConfig: {
        responseMimeType: "application/json",
        responseSchema: profileSchema as any,
      },
    });

    const pdfBuffer = await readFile(req.file.path);
    const pdfBase64 = pdfBuffer.toString("base64");

    const prompt = `
You are a Grant Matching Specialist AI. Analyze the attached research project PDF and extract a structured profile to match the researcher with funding opportunities.

INSTRUCTIONS:
1. Identify the core technical domain, methods, and application areas.
2. Extract terms that should be searched for in funding opportunities (include terms).
3. Identify irrelevant domains to exclude (exclude terms).
4. Propose scoring weights that reflect the project's priorities.
5. Set thresholds: go (strong match), watch (potential match).
6. Return ONLY valid JSON matching the schema.
`;

    const result = await model.generateContent([
      { text: prompt },
      {
        inlineData: {
          mimeType: "application/pdf",
          data: pdfBase64,
        },
      },
    ]);

    const text = result.response.text();
    const data = JSON.parse(text);

    // Enrich with metadata
    const fullProfile = {
      ...data,
      source_pdf: req.file.originalname,
      last_updated: new Date().toISOString().split("T")[0],
    };

    // Save to data dir
    await mkdir(DATA_DIR, { recursive: true });
    await writeFile(
      join(DATA_DIR, "mestrado_profile_requirements.json"),
      JSON.stringify(fullProfile, null, 2) + "\n",
      "utf8"
    );

    // Also copy to static-api
    await mkdir(join(DATA_DIR, "static-api"), { recursive: true });
    await copyFile(
      join(DATA_DIR, "mestrado_profile_requirements.json"),
      join(DATA_DIR, "static-api", "profile.json")
    );

    res.json({ success: true, profile: fullProfile });
  } catch (error: any) {
    console.error("Analyze profile PDF error:", error);
    res.status(500).json({ error: error.message || "Failed to analyze PDF" });
  }
});

app.post("/api/refresh", async (_req, res) => {
  try {
    // Execute the pipeline to fetch new opportunities
    const { stdout, stderr } = await execAsync("node dist/main.js", {
      cwd: process.cwd(),
      env: { ...process.env, NODE_ENV: "production" },
      timeout: 300_000, // 5 minutes max
    });

    console.log("Pipeline stdout:", stdout);
    if (stderr) {
      console.error("Pipeline stderr:", stderr);
    }

    // Read the updated opportunities and status
    const [opportunitiesData, statusData] = await Promise.all([
      readFile(join(DATA_DIR, "static-api", "opportunities.json"), "utf8").catch(() => "[]"),
      readFile(join(DATA_DIR, "static-api", "status.json"), "utf8").catch(() => "{}"),
    ]);

    res.json({
      opportunities: JSON.parse(opportunitiesData),
      status: JSON.parse(statusData),
      message: "Pipeline executed successfully",
      log: stdout,
    });
  } catch (error: any) {
    console.error("Pipeline execution error:", error);
    res.status(500).json({
      error: "Pipeline execution failed",
      detail: error.message || String(error),
    });
  }
});

// Fallback: serve index.html for SPA routes
app.use((_req, res) => {
  res.sendFile(join(STATIC_DIR, "index.html"));
});

app.listen(PORT, HOST, () => {
  console.log(`GrantWatch server running at http://${HOST}:${PORT}`);
});
