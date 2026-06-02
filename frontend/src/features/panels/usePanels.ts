import { useState } from 'react'

export function usePanels() {
    const [ragDebugOpen, setRagDebugOpen] = useState(false)
    const [memoryOpen, setMemoryOpen] = useState(false)
    const [canvasOpen, setCanvasOpen] = useState(false)
    const [researchOpen, setResearchOpen] = useState(false)
    const [imagesOpen, setImagesOpen] = useState(false)
    const [sidebarOpen, setSidebarOpen] = useState(false)
    const [canvasSeed, setCanvasSeed] = useState('')
    const [canvasVersion, setCanvasVersion] = useState(0)

    function sendToCanvas(content: string) {
        setCanvasSeed(content)
        setCanvasVersion((value) => value + 1)
        setCanvasOpen(true)
    }

    return {
        ragDebugOpen,
        memoryOpen,
        canvasOpen,
        researchOpen,
        imagesOpen,
        sidebarOpen,
        canvasSeed,
        canvasVersion,
        setRagDebugOpen,
        setMemoryOpen,
        setCanvasOpen,
        setResearchOpen,
        setImagesOpen,
        setSidebarOpen,
        setCanvasSeed,
        sendToCanvas,
    }
}

