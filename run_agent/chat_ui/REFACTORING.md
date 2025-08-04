# Chat UI Refactoring

This document describes the refactoring of the large `App.tsx` component into smaller, more manageable modules.

## Structure Overview

The refactored codebase is organized into the following directories:

### `/src/types/`
- **`index.ts`** - All TypeScript type definitions and interfaces

### `/src/utils/`
- **`index.ts`** - Utility functions like `randomUUID`, `getRandomString`, and style injection

### `/src/services/`
- **`api.ts`** - API service functions including `MockChatHistoryAPI` and `getAgentState`
- **`messageMapper.ts`** - Functions to map between different message formats
- **`index.ts`** - Service exports

### `/src/hooks/`
- **`useChatState.ts`** - Custom hook for managing chat messages, current message, and token usage
- **`useChatHistory.ts`** - Custom hook for managing chat threads and history
- **`useAgentService.ts`** - Custom hook for agent communication, event handling, and user interrupts (merged from useInterruptHandler)
- **`index.ts`** - Hook exports

### `/src/components/`
- **`ChatHistorySidebar.tsx`** - Sidebar component showing chat history and threads
- **`ChatHeader.tsx`** - Header component with controls and token usage display
- **`ChatInput.tsx`** - Input component for user messages
- **`ChatMessage.tsx`** - Component for rendering individual chat messages
- **`CurrentMessage.tsx`** - Component for rendering the currently streaming message
- **`InterruptPrompt.tsx`** - Component for handling user interrupts
- **`ChatMessagesContainer.tsx`** - Container component for all chat messages
- **`index.ts`** - Component exports

## Key Improvements

### 1. **Separation of Concerns**
- **UI Components**: Pure presentation components with clear props interfaces
- **Business Logic**: Moved to custom hooks for reusability
- **API Layer**: Centralized in services directory
- **State Management**: Organized into focused custom hooks

### 2. **File Size Reduction**
- Original `App.tsx`: 1,734 lines
- Refactored `App.tsx`: ~200 lines (further reduced after hook consolidation)
- Individual components/hooks: < 450 lines each (largest is now the merged useAgentService)
- Most files remain under 200 lines each as requested

### 3. **Reusability**
- Components can be easily reused in other parts of the application
- Hooks can be shared across multiple components
- Services provide centralized API access

### 4. **Maintainability**
- Clear file organization makes it easy to locate specific functionality
- Smaller files are easier to understand and modify
- Type definitions are centralized for consistency

### 5. **Testability**
- Individual components and hooks can be unit tested in isolation
- Services can be mocked for testing
- Clear separation makes integration testing easier

## Component Breakdown

### UI Components
1. **ChatHistorySidebar** - Manages chat thread display and navigation
2. **ChatHeader** - Application header with controls and status indicators
3. **ChatInput** - User input handling with send functionality
4. **ChatMessage** - Individual message rendering (user, assistant, tool, interrupt)
5. **CurrentMessage** - Streaming message display with real-time updates
6. **InterruptPrompt** - Interactive prompt for agent interrupts
7. **ChatMessagesContainer** - Container managing message flow and layout

### Custom Hooks
1. **useChatState** - Core chat state management (messages, streaming, tokens)
2. **useChatHistory** - Thread management and history persistence
3. **useAgentService** - Agent communication, event processing, and interrupt handling (merged functionality)

### Services
1. **MockChatHistoryAPI** - Simulated backend for chat persistence
2. **getAgentState** - Real backend state retrieval
3. **mapStateMessagesToAGUI** - Message format transformation

## Usage Example

```tsx
import { useState } from "react";
import { useChatState, useChatHistory, useAgentService } from "./hooks";
import { ChatHeader, ChatInput, ChatMessagesContainer } from "./components";

function MyApp() {
  const chatState = useChatState();
  const chatHistory = useChatHistory();
  const agentService = useAgentService(/* ... */);
  
  return (
    <div>
      <ChatHeader /* ... */ />
      <ChatInput /* ... */ />
      <ChatMessagesContainer /* ... */ />
    </div>
  );
}
```

## Recent Changes

### Hook Consolidation (Latest)
- **Merged `useInterruptHandler` into `useAgentService`**: Combined interrupt handling functionality into the main agent service hook for better cohesion
- **Reduced hook count**: From 4 custom hooks to 3, simplifying the API surface
- **Improved maintainability**: Related functionality (agent communication and interrupts) is now co-located
- **Single responsibility**: The agent service hook now handles all agent-related operations including interrupts
- **Reduced complexity**: Eliminates the need to coordinate between separate hooks for agent operations
- **Updated exports**: Removed `useInterruptHandler` from hook exports and updated documentation
- **File consolidation**: Removed `useInterruptHandler.ts` (103 lines) and merged into `useAgentService.ts` (433 lines)

## Migration Notes

- The original `App.tsx` is preserved as `App.old.tsx`
- All functionality has been preserved during refactoring
- Components use inline styles to maintain visual consistency
- TypeScript types have been properly applied throughout

## Future Improvements

1. **Styling**: Consider moving inline styles to CSS modules or styled-components
2. **State Management**: Could integrate with Redux or Zustand for complex state needs
3. **Error Boundaries**: Add error boundaries for better error handling
4. **Testing**: Add comprehensive unit and integration tests
5. **Performance**: Add React.memo for components that don't change frequently
