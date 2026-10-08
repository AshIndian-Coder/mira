import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from '../context/AuthContext'
import { OperationProvider } from '../context/OperationContext'
import AppRoutes from './routes'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <OperationProvider>
          <AppRoutes />
        </OperationProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App