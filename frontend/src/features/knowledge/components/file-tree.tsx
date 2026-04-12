import { useState } from "react"
import { ChevronRight, Folder as FolderIcon, FolderOpen } from "lucide-react"
import { cn } from "@/lib/utils"
import type { Folder } from "@/api/knowledge"

interface FileTreeProps {
  folders: Folder[]
  selectedFolderId: string | null
  onSelectFolder: (id: string | null) => void
}

export function FileTree({ folders, selectedFolderId, onSelectFolder }: FileTreeProps) {
  return (
    <div className="flex flex-col gap-0.5 text-sm">
      <button
        type="button"
        className={cn(
          "flex items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-muted",
          selectedFolderId === null && "bg-muted font-medium",
        )}
        onClick={() => onSelectFolder(null)}
      >
        <FolderIcon className="size-4 text-muted-foreground" />
        全部文档
      </button>
      {folders.map((folder) => (
        <FolderNode
          key={folder.id}
          folder={folder}
          depth={0}
          selectedFolderId={selectedFolderId}
          onSelectFolder={onSelectFolder}
        />
      ))}
    </div>
  )
}

interface FolderNodeProps {
  folder: Folder
  depth: number
  selectedFolderId: string | null
  onSelectFolder: (id: string | null) => void
}

function FolderNode({ folder, depth, selectedFolderId, onSelectFolder }: FolderNodeProps) {
  const [expanded, setExpanded] = useState(false)
  const hasChildren = folder.children && folder.children.length > 0
  const isSelected = selectedFolderId === folder.id

  return (
    <div>
      <button
        type="button"
        className={cn(
          "flex w-full items-center gap-1 rounded-md px-2 py-1.5 text-left hover:bg-muted",
          isSelected && "bg-muted font-medium",
        )}
        style={{ paddingLeft: `${(depth + 1) * 12 + 8}px` }}
        onClick={() => onSelectFolder(folder.id)}
      >
        {hasChildren ? (
          <ChevronRight
            className={cn("size-3.5 shrink-0 transition-transform", expanded && "rotate-90")}
            onClick={(e) => {
              e.stopPropagation()
              setExpanded(!expanded)
            }}
          />
        ) : (
          <span className="w-3.5" />
        )}
        {expanded ? (
          <FolderOpen className="size-4 shrink-0 text-muted-foreground" />
        ) : (
          <FolderIcon className="size-4 shrink-0 text-muted-foreground" />
        )}
        <span className="truncate">{folder.name}</span>
        <span className="ml-auto text-xs text-muted-foreground">{folder.doc_count}</span>
      </button>
      {expanded && hasChildren && (
        <div>
          {folder.children!.map((child) => (
            <FolderNode
              key={child.id}
              folder={child}
              depth={depth + 1}
              selectedFolderId={selectedFolderId}
              onSelectFolder={onSelectFolder}
            />
          ))}
        </div>
      )}
    </div>
  )
}
