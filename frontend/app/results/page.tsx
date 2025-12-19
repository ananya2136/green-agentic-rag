"use client"

import { motion } from "framer-motion"
import { useState, useEffect, useRef, Suspense } from "react"
import { useSearchParams } from "next/navigation"
import { Sidebar } from "@/components/sidebar"
import { TopBar } from "@/components/top-bar"
import { LiveFeed } from "@/components/live-feed"
import { Card } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Leaf, Zap, Star, Copy, Download } from "lucide-react"
import { Button } from "@/components/ui/button"

// Types for backend data
interface JobStatus {
  status: string
  progress: number
  message: string
}

interface CarbonData {
  carbon_saved_grams: number
  baseline_cost_gco2e: number
  actual_cost_gco2e: number
  efficiency_percent: number
  total_chunks: number
  chunks_escalated: number
  compute_location: string
  local_grid_gco2_kwh: number
  message: string
}

interface JobResult {
  job_id: string
  document_id: string
  filename: string
  final_summary: string
  carbon_data: CarbonData
}

interface ChatMessage {
  role: "user" | "assistant"
  content: string
}

function ResultsContent() {
  const searchParams = useSearchParams()
  const jobId = searchParams.get("job_id")

  const [isComplete, setIsComplete] = useState(false)
  const [logs, setLogs] = useState<any[]>([])
  const [result, setResult] = useState<JobResult | null>(null)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState("")
  const [isChatLoading, setIsChatLoading] = useState(false)

  useEffect(() => {
    if (!jobId) return

    let pollInterval: NodeJS.Timeout

    const pollStatus = async () => {
      try {
        const response = await fetch(`http://localhost:8000/job-status/${jobId}`)
        if (response.ok) {
          const data: JobStatus = await response.json()

          // Update logs (simulated from status message for now, or append real logs if backend provided them)
          setLogs(prev => {
            const newLog = {
              id: Date.now().toString(),
              timestamp: new Date().toLocaleTimeString(),
              message: data.message,
              type: data.status === 'error' ? 'error' : 'info'
            }
            // Avoid duplicate messages if possible, or just show latest
            if (prev.length > 0 && prev[prev.length - 1].message === data.message) return prev
            return [...prev, newLog]
          })

          if (data.status === 'complete') {
            setIsComplete(true)
            clearInterval(pollInterval)
            fetchResult()
          } else if (data.status === 'error') {
            clearInterval(pollInterval)
            alert(`Job failed: ${data.message}`)
          }
        }
      } catch (error) {
        console.error("Polling error:", error)
      }
    }

    pollInterval = setInterval(pollStatus, 2000)
    pollStatus() // Initial call

    return () => clearInterval(pollInterval)
  }, [jobId])

  const fetchResult = async () => {
    try {
      const response = await fetch(`http://localhost:8000/job-result/${jobId}`)
      if (response.ok) {
        const data: JobResult = await response.json()
        setResult(data)
        // Initialize chat with a greeting
        setChatMessages([{ role: "assistant", content: "Your document is ready! I've read the summary and can now answer your questions." }])
      }
    } catch (error) {
      console.error("Error fetching result:", error)
    }
  }

  const handleCopy = () => {
    if (result?.final_summary) {
      navigator.clipboard.writeText(result.final_summary)
      alert("Summary copied to clipboard!")
    }
  }

  const handleDownload = () => {
    if (result?.final_summary) {
      const blob = new Blob([result.final_summary], { type: "text/plain" })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `summary-${result.filename || "document"}.txt`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }
  }

  const handleChatSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!chatInput.trim() || !result) return

    const userMsg = chatInput
    setChatMessages(prev => [...prev, { role: "user", content: userMsg }])
    setChatInput("")
    setIsChatLoading(true)

    try {
      const response = await fetch("http://localhost:8000/rag-query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_id: result.document_id,
          query: userMsg
        })
      })

      if (response.ok) {
        const data = await response.json()
        let fullAnswer = data.answer
        if (data.sources && data.sources.length > 0) {
          fullAnswer += "\n\n---\nSources:\n" + data.sources.slice(0, 2).map((s: string) => `* ${s.substring(0, 150)}...`).join("\n")
        }
        setChatMessages(prev => [...prev, { role: "assistant", content: fullAnswer }])
      } else {
        setChatMessages(prev => [...prev, { role: "assistant", content: "Sorry, I encountered an error answering that." }])
      }
    } catch (error) {
      console.error("Chat error:", error)
      setChatMessages(prev => [...prev, { role: "assistant", content: "Connection error." }])
    } finally {
      setIsChatLoading(false)
    }
  }

  return (
    <div className="flex">
      <Sidebar />
      <div className="flex-1">
        <TopBar />
        <main className="p-8">
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <h1 className="text-3xl font-bold mb-2">Job Status & Results</h1>
            <p className="text-muted-foreground mb-8">Job ID: {jobId || "Loading..."}</p>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
              {/* Job Report Card */}
              <motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.2 }}
                className="lg:col-span-1"
              >
                <Card className="p-6 bg-gradient-to-br from-card to-card/50 border-border/50 sticky top-20">
                  <h3 className="text-lg font-semibold mb-4">Job Report Card</h3>

                  {result ? (
                    <div className="space-y-4">
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Job ID</p>
                        <p className="font-mono text-sm">{result.job_id}</p>
                      </div>

                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Mode</p>
                        <p className="font-medium">Eco-Mode</p>
                      </div>

                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <Leaf className="w-4 h-4 text-green-400" />
                          <span className="text-sm text-muted-foreground">Carbon Saved</span>
                        </div>
                        <p className="text-2xl font-bold ml-6">{result.carbon_data.carbon_saved_grams?.toFixed(4) || "0.0000"}g CO2e</p>
                      </div>

                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <Star className="w-4 h-4 text-amber-400" />
                          <span className="text-sm text-muted-foreground">Baseline Cost</span>
                        </div>
                        <p className="text-2xl font-bold ml-6">{result.carbon_data.baseline_cost_gco2e?.toFixed(4) || "0.0000"}g CO2e</p>
                      </div>

                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <Zap className="w-4 h-4 text-blue-400" />
                          <span className="text-sm text-muted-foreground">Efficiency</span>
                        </div>
                        <p className="text-2xl font-bold ml-6">{result.carbon_data.efficiency_percent?.toFixed(0) || "0"}%</p>
                      </div>

                      <div>
                        <p className="text-xs text-muted-foreground mb-2">Compute Location</p>
                        <p className="text-sm">{result.carbon_data.compute_location || "Unknown"}</p>
                      </div>
                    </div>
                  ) : (
                    <div className="text-muted-foreground text-sm">Waiting for results...</div>
                  )}
                </Card>
              </motion.div>

              {/* Main Content */}
              <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.2 }}
                className="lg:col-span-2"
              >
                {!isComplete ? (
                  <LiveFeed logs={logs} />
                ) : (
                  <Tabs defaultValue="summary" className="w-full">
                    <TabsList className="grid w-full grid-cols-2">
                      <TabsTrigger value="summary">Summary</TabsTrigger>
                      <TabsTrigger value="chat">Chat (RAG)</TabsTrigger>
                    </TabsList>

                    <TabsContent value="summary" className="space-y-4">
                      <Card className="p-6 bg-card/50 border-border/50">
                        <div className="flex gap-4 mb-6">
                          <Button size="sm" variant="outline" className="gap-2 bg-transparent" onClick={handleCopy}>
                            <Copy className="w-4 h-4" />
                            Copy
                          </Button>
                          <Button size="sm" variant="outline" className="gap-2 bg-transparent" onClick={handleDownload}>
                            <Download className="w-4 h-4" />
                            Download
                          </Button>
                        </div>
                        <div className="prose prose-invert max-w-none">
                          <div className="text-sm leading-relaxed whitespace-pre-wrap text-foreground">
                            {result?.final_summary}
                          </div>
                        </div>
                      </Card>
                    </TabsContent>

                    <TabsContent value="chat" className="space-y-4">
                      <Card className="p-6 bg-card/50 border-border/50 h-[600px] flex flex-col">
                        <div className="flex-1 overflow-y-auto mb-4 space-y-4 p-2">
                          {chatMessages.map((msg, idx) => (
                            <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                              <div className={`max-w-[80%] rounded-lg p-3 ${msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'}`}>
                                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                              </div>
                            </div>
                          ))}
                          {isChatLoading && <div className="text-sm text-muted-foreground">Thinking...</div>}
                        </div>
                        <form onSubmit={handleChatSubmit} className="flex gap-2">
                          <input
                            type="text"
                            value={chatInput}
                            onChange={(e) => setChatInput(e.target.value)}
                            placeholder="Ask a question about the document..."
                            className="flex-1 px-4 py-2 rounded-lg bg-background border border-border/50 placeholder-muted-foreground focus:outline-none focus:border-primary"
                          />
                          <Button type="submit" disabled={isChatLoading}>Send</Button>
                        </form>
                      </Card>
                    </TabsContent>
                  </Tabs>
                )}
              </motion.div>
            </div>
          </motion.div>
        </main>
      </div>
    </div>
  )
}

export default function ResultsPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <ResultsContent />
    </Suspense>
  )
}
