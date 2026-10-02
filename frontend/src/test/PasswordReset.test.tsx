import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ForgotPasswordPage } from "../pages/auth/ForgotPasswordPage";
import { ResetPasswordPage } from "../pages/auth/ResetPasswordPage";

const requestPasswordReset = vi.fn();
const confirmPasswordReset = vi.fn();

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: null,
    isLoading: false,
    setupRequired: false,
    requestPasswordReset,
    confirmPasswordReset,
  }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

function renderWithRouter(ui: React.ReactElement, initialPath = "/") {
  return render(<MemoryRouter initialEntries={[initialPath]}>{ui}</MemoryRouter>);
}

describe("ForgotPasswordPage", () => {
  it("renders the email form", () => {
    renderWithRouter(<ForgotPasswordPage />);
    expect(screen.getByPlaceholderText("admin@actioncenter.com")).toBeInTheDocument();
    expect(screen.getByText("Send reset link")).toBeInTheDocument();
  });

  it("shows confirmation after submitting", async () => {
    requestPasswordReset.mockResolvedValue(undefined);
    renderWithRouter(<ForgotPasswordPage />);
    fireEvent.change(screen.getByPlaceholderText("admin@actioncenter.com"), {
      target: { value: "user@example.com" },
    });
    fireEvent.click(screen.getByText("Send reset link"));
    await waitFor(() => expect(requestPasswordReset).toHaveBeenCalledWith("user@example.com"));
    expect(await screen.findByText("Check your email")).toBeInTheDocument();
  });

  it("shows an error when the request fails", async () => {
    requestPasswordReset.mockRejectedValue(new Error("Server error"));
    renderWithRouter(<ForgotPasswordPage />);
    fireEvent.change(screen.getByPlaceholderText("admin@actioncenter.com"), {
      target: { value: "user@example.com" },
    });
    fireEvent.click(screen.getByText("Send reset link"));
    expect(await screen.findByText("Server error")).toBeInTheDocument();
  });
});

describe("ResetPasswordPage", () => {
  it("warns when the token is missing", () => {
    renderWithRouter(<ResetPasswordPage />, "/reset-password");
    expect(screen.getByText(/invalid or missing its token/i)).toBeInTheDocument();
  });

  it("rejects mismatched passwords client-side", async () => {
    renderWithRouter(<ResetPasswordPage />, "/reset-password?token=abc");
    fireEvent.change(screen.getByPlaceholderText("At least 8 characters"), {
      target: { value: "NewPass123" },
    });
    fireEvent.change(screen.getByPlaceholderText("Repeat your new password"), {
      target: { value: "Different1" },
    });
    fireEvent.click(screen.getByText("Reset password"));
    expect(await screen.findByText("Passwords do not match")).toBeInTheDocument();
    expect(confirmPasswordReset).not.toHaveBeenCalled();
  });

  it("confirms reset on success and shows sign-in prompt", async () => {
    confirmPasswordReset.mockResolvedValue(undefined);
    renderWithRouter(<ResetPasswordPage />, "/reset-password?token=abc");
    fireEvent.change(screen.getByPlaceholderText("At least 8 characters"), {
      target: { value: "NewPass123" },
    });
    fireEvent.change(screen.getByPlaceholderText("Repeat your new password"), {
      target: { value: "NewPass123" },
    });
    fireEvent.click(screen.getByText("Reset password"));
    await waitFor(() => expect(confirmPasswordReset).toHaveBeenCalledWith("abc", "NewPass123"));
    expect(await screen.findByText("Password reset")).toBeInTheDocument();
  });
});
