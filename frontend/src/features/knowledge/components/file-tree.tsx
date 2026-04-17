import { useState } from "react"
import { ChevronRight, Folder as FolderIcon, FolderOpen, MoreHorizontal, Plus } from "lucide-react"
import { toast } from "sonner"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { PromptDialog } from "@/components/shared/prompt-dialog"
import { knowledgeApi, type Folder } from "@/api/knowledge"

interface FileTreeProps {
  kbId: string
  folders: Folder[]
  selectedFolderId: string | null
  onSelectFolder: (id: string | null) => void
  onFoldersChanged?: () => void
}

type CreateTarget = { parentId: string | null } | null
type RenameTarget = Folder | null
type DeleteTarget = Folder | null

/**
 * Folder-only tree for the Documents tab left column. Files (documents) live
 * in the middle column. Folder ops exposed via `···` hover menu. Uses themed
 * Dialog components instead of window.prompt/confirm for visual consistency.
 */
export function FileTree({ kbId, folders, selectedFolderId, onSelectFolder, onFoldersChanged }: FileTreeProps) {
  const [createTarget, setCreateTarget] = useState<CreateTarget>(null)
  const [renameTarget, setRenameTarget] = useState<RenameTarget>(null)
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>(null)

  async function doCreate(name: string) {
    if (!createTarget) return
    await knowledgeApi.createFolder(kbId, {
      name,
      parent_folder_id: createTarget.parentId || undefined,
    })
    toast.success("文件夹已创建")
    onFoldersChanged?.()
  }

  async function doRename(name: string) {
    if (!renameTarget) return
    await knowledgeApi.updateFolder(kbId, renameTarget.id, { name })
    toast.success("重命名成功")
    onFoldersChanged?.()
  }

  async function doDelete() {
    if (!deleteTarget) return
    try {
      await knowledgeApi.deleteFolder(kbId, deleteTarget.id)
      toast.success("文件夹已删除")
      if (selectedFolderId === deleteTarget.id) onSelectFolder(null)
      onFoldersChanged?.()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败")
    }
  }

  return (
    <>
      <div className="flex flex-col gap-0.5 text-sm">
        {/* Root: all docs */}
        <div
          className={cn(
            "group flex items-center rounded-md pr-1 hover:bg-accent cursor-pointer",
            selectedFolderId === null && "bg-accent font-medium text-accent-foreground",
          )}
          onClick={() => onSelectFolder(null)}
        >
          <div className="flex flex-1 items-center gap-2 px-2 py-1.5">
            <FolderIcon className="size-4 text-muted-foreground" />
            <span className="flex-1 truncate">全部文档</span>
          </div>
          <FolderOpsMenu
            onCreateChild={() => setCreateTarget({ parentId: null })}
          />
        </div>

        {folders.map((folder) => (
          <FolderNode
            key={folder.id}
            folder={folder}
            depth={0}
            selectedFolderId={selectedFolderId}
            onSelectFolder={onSelectFolder}
            onRequestCreate={(pid) => setCreateTarget({ parentId: pid })}
            onRequestRename={(f) => setRenameTarget(f)}
            onRequestDelete={(f) => setDeleteTarget(f)}
          />
        ))}

        {folders.length === 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="mt-1 justify-start text-muted-foreground"
            onClick={() => setCreateTarget({ parentId: null })}
          >
            <Plus className="mr-1 size-3.5" /> 新建文件夹
          </Button>
        )}
      </div>

      <PromptDialog
        open={createTarget !== null}
        onOpenChange={(v) => { if (!v) setCreateTarget(null) }}
        title="新建文件夹"
        label="文件夹名称"
        placeholder="例如：故障排查"
        confirmText="创建"
        onConfirm={doCreate}
      />

      <PromptDialog
        open={renameTarget !== null}
        onOpenChange={(v) => { if (!v) setRenameTarget(null) }}
        title="重命名文件夹"
        label="新名称"
        defaultValue={renameTarget?.name ?? ""}
        confirmText="保存"
        validate={(v) => v === renameTarget?.name ? "请输入不同的名称" : null}
        onConfirm={doRename}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title="删除文件夹"
        description={`确认删除文件夹 "${deleteTarget?.name ?? ""}"？其下内容将一并处理，此操作不可撤销。`}
        confirmText="删除"
        destructive
        onConfirm={doDelete}
      />
    </>
  )
}

interface FolderNodeProps {
  folder: Folder
  depth: number
  selectedFolderId: string | null
  onSelectFolder: (id: string | null) => void
  onRequestCreate: (parentId: string) => void
  onRequestRename: (folder: Folder) => void
  onRequestDelete: (folder: Folder) => void
}

function FolderNode({
  folder, depth, selectedFolderId, onSelectFolder,
  onRequestCreate, onRequestRename, onRequestDelete,
}: FolderNodeProps) {
  const [expanded, setExpanded] = useState(false)
  const hasChildren = folder.children && folder.children.length > 0
  const isSelected = selectedFolderId === folder.id

  return (
    <div>
      <div
        className={cn(
          "group flex items-center rounded-md pr-1 hover:bg-accent cursor-pointer",
          isSelected && "bg-accent font-medium text-accent-foreground",
        )}
        onClick={() => onSelectFolder(folder.id)}
      >
        <div
          className="flex flex-1 items-center gap-1 py-1.5 pr-2 min-w-0"
          style={{ paddingLeft: `${(depth + 1) * 12 + 8}px` }}
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
            <FolderOpen className="size-4 shrink-0 text-primary" />
          ) : (
            <FolderIcon className="size-4 shrink-0 text-muted-foreground" />
          )}
          <span className="truncate">{folder.name}</span>
        </div>
        <FolderOpsMenu
          onCreateChild={() => onRequestCreate(folder.id)}
          onRename={() => onRequestRename(folder)}
          onDelete={() => onRequestDelete(folder)}
        />
      </div>

      {expanded && hasChildren && (
        <div>
          {folder.children!.map((child) => (
            <FolderNode
              key={child.id}
              folder={child}
              depth={depth + 1}
              selectedFolderId={selectedFolderId}
              onSelectFolder={onSelectFolder}
              onRequestCreate={onRequestCreate}
              onRequestRename={onRequestRename}
              onRequestDelete={onRequestDelete}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function FolderOpsMenu({
  onCreateChild, onRename, onDelete,
}: {
  onCreateChild: () => void
  onRename?: () => void
  onDelete?: () => void
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button
            type="button"
            className="inline-flex size-6 shrink-0 items-center justify-center rounded opacity-0 transition-opacity hover:bg-background/60 group-hover:opacity-100 data-[state=open]:opacity-100 data-[state=open]:bg-background/60"
            title="操作"
            // Prevent the click from bubbling up to the row's onClick
            // (which would select the folder instead of opening the menu).
            onClick={(e) => e.stopPropagation()}
          />
        }
      >
        <MoreHorizontal className="size-3.5" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="text-sm" onClick={(e) => e.stopPropagation()}>
        <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onCreateChild() }}>新建子文件夹</DropdownMenuItem>
        {onRename && <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onRename() }}>重命名</DropdownMenuItem>}
        {onDelete && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onDelete() }} className="text-destructive">删除</DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
