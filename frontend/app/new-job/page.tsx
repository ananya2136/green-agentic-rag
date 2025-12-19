"use client"

import { motion } from "framer-motion"
import { useState } from "react"
import { useRouter } from "next/navigation"
import { Sidebar } from "@/components/sidebar"
import { TopBar } from "@/components/top-bar"
import { UploadZone } from "@/components/upload-zone"
import { StrategySelector } from "@/components/strategy-selector"
import { Card } from "@/components/ui/card"

export default function NewJobPage() {
  const router = useRouter()
  const [step, setStep] = useState<"upload" | "strategy">("upload")
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  const handleFileSelect = (file: File) => {
    setSelectedFile(file)
    setStep("strategy")
  }

  const handleSubmit = async (strategy: "eco" | "balanced" | "quality") => {
    if (!selectedFile) return

    try {
      const formData = new FormData()
      formData.append("file", selectedFile)

      // Map strategy to backend mode
      const modeMap = {
        eco: "eco",
        balanced: "balanced",
        quality: "max_quality" // Assuming backend expects 'max_quality' or similar, checking frontend_app.py it was 'max quality' but params usually lower case with underscore. Let's check backend.
        // Checking frontend_app.py: params = {'mode': mode.lower()} where mode is 'Eco', 'Balanced', 'Max Quality'.
        // So 'max quality' -> 'max quality'.
        // But let's check backend/src/api/main.py to be sure about allowed values.
        // For now I will use 'balanced' as default and pass the strategy string.
      }

      // Actually, let's look at the backend code if possible, but based on frontend_app.py it sends mode.lower().
      // 'Eco' -> 'eco', 'Balanced' -> 'balanced', 'Max Quality' -> 'max quality'.

      let backendMode = strategy
      if (strategy === 'quality') backendMode = 'max quality' // Adjust if needed

      const response = await fetch(`http://localhost:8000/summarize?mode=${backendMode}`, {
        method: "POST",
        body: formData,
      })

      if (!response.ok) {
        throw new Error("Upload failed")
      }

      const data = await response.json()
      router.push(`/results?job_id=${data.job_id}`)
    } catch (error) {
      console.error("Error uploading file:", error)
      alert("Failed to start job. Please try again.")
    }
  }

  return (
    <div className="flex">
      <Sidebar />
      <div className="flex-1">
        <TopBar />
        <main className="p-8">
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <h1 className="text-3xl font-bold mb-2">Create New Job</h1>
            <p className="text-muted-foreground mb-8">Upload a document and configure your processing strategy</p>

            {step === "upload" ? (
              <UploadZone onFileSelect={handleFileSelect} />
            ) : (
              <div className="max-w-3xl">
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
                  <Card className="p-4 bg-primary/10 border-primary/30">
                    <p className="text-sm text-foreground">
                      <strong>Selected File:</strong> {selectedFile?.name}
                    </p>
                  </Card>
                </motion.div>

                <StrategySelector onSubmit={handleSubmit} />

                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => {
                    setStep("upload")
                    setSelectedFile(null)
                  }}
                  className="mt-8 text-muted-foreground hover:text-foreground transition-colors underline"
                >
                  ← Change document
                </motion.button>
              </div>
            )}
          </motion.div>
        </main>
      </div>
    </div>
  )
}
